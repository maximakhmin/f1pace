import pandas as pd
import xgboost as xgb
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


load_dotenv()
engine = create_engine(f'postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@localhost:5432/f1pace')

model = xgb.XGBRegressor()
model.load_model("web_app/xgboost_with_rain.ubj")

query_laps = """
    WITH 
    stints_with_end AS (
        SELECT 
            *,
            -- Находим круг начала следующего стинта для этого же водителя
            LEAD(start_lap) OVER (PARTITION BY driver_number ORDER BY start_lap) AS end_lap
        FROM real_time_stints
    ),
    laps_with_start_time as (
        SELECT 
            *,
            LAG(end_time_utc) OVER (
                PARTITION BY driver_number 
                ORDER BY lap_number
            ) AS start_time_utc
        FROM real_time_laps
    ),
    laps_with_weather as (
        SELECT 
            l.*,
            s.*,
            w.*,
            l.driver_number as dr_num,
            ROW_NUMBER() OVER (
                PARTITION BY l.id
                ORDER BY w.time_utc DESC
            ) as rn
        FROM laps_with_start_time l
        LEFT JOIN stints_with_end s 
            ON l.driver_number = s.driver_number
            AND l.lap_number >= s.start_lap
            -- Если это последний стинт, end_lap будет NULL, поэтому используем COALESCE
            AND l.lap_number < COALESCE(s.end_lap, 999999)
        left join real_time_weather w
            on w.time_utc <= l.start_time_utc 
    )
    select
        l.dr_num driver_number,
        l.lap_time,
        l.lap_number,
        l.stint_number,
        l.tyre_type,
        l.lap_number + l.total_laps - l.start_lap + 1 as tyre_age,
        
        l.end_time_utc, 
        l.air_temp,
        l.humidity,
        l.pressure,
        l.is_rain,
        l.track_temp,
        l.wind_direction,
        l.wind_speed
    from laps_with_weather l
    where rn=1

    order by driver_number, stint_number, lap_number
"""
target_column = ['lap_time']
feature_columns = [
    'tyre_type', 'tyre_age', 'lap_number',
    'grip', 'abrasion', 'downforce', 'lateralis', 'braking', 'traction', 
    'is_rain', 'air_temp', 'track_temp', 'humidity', 'wind_direction', 'wind_speed',
    
    'shift_1_lap_time', 'shift_2_lap_time',
    'shift_1_is_rain',
    'shift_1_air_temp',
    'shift_1_track_temp', 
    'shift_1_humidity',
    'shift_1_wind_direction', 
    'shift_1_wind_speed',
]
return_columns = [
    'driver_number', 'lap_time', 'lap_number', 'stint_number', 'tyre_type',
    'tyre_age', 'end_time_utc', 'is_predicted_future',
]
columns_to_shift = [
    'lap_time', 
    'air_temp', 'track_temp', 'humidity', 'is_rain', 
    'wind_direction', 'wind_speed',
]

def predict_future_laps(session_id, n_laps=5):
    """
    Итеративно предсказывает n_laps кругов вперед для каждого стинта (driver + stint).
    """
    query_track = f"""
        SELECT grip, abrasion, downforce, lateralis, braking, traction 
        FROM tracks_enriched te 
        join events e on e.track_id = te.id 
        join sessions s on s.event_id = e.id
        where s.id = {session_id}
    """

    df_laps = pd.read_sql(query_laps, engine)
    df_track = pd.read_sql(query_track, engine)
    df = pd.merge(df_laps, df_track, 'cross')

    df_shifted_1 = df.groupby(['driver_number', 'stint_number'])[columns_to_shift].shift(1)
    df_shifted_2 = df.groupby(['driver_number', 'stint_number'])[columns_to_shift].shift(2)

    for col in columns_to_shift:
        df[f'shift_1_{col}'] = df_shifted_1[col]
        df[f'shift_2_{col}'] = df_shifted_2[col]


    # 1. Сортируем для правильной хронологии
    df = df.sort_values(by=['driver_number', 'lap_number']).reset_index(drop=True)
    
    # Список для сбора будущих предсказанных кругов
    future_laps_list = []
    
    # Группируем по уникальным стинтам
    grouped = df.groupby(['driver_number'])
    
    for (driver_number, ), group in grouped:
        if group.empty:
            continue
            
        # Берем самый последний известный круг в этом стинте как отправную точку
        last_known_lap = group.iloc[-1].copy()
        
        # Переменные для отслеживания истории (авторегрессия)
        # Нам нужны лаги на 1 и 2 шага назад для самого первого предсказания
        # shift_1 — это время только что законченного (последнего известного) круга
        # shift_2 — это время предпоследнего круга
        pred_shift_1 = last_known_lap['lap_time']
        
        if len(group) > 1:
            pred_shift_2 = group.iloc[-2]['lap_time']
        else:
            # Если в стинте был всего 1 круг, берем его же или shift_1_lap_time из фичей
            pred_shift_2 = last_known_lap['shift_1_lap_time']
            
        current_lap_num = last_known_lap['lap_number']
        current_tyre_age = last_known_lap['tyre_age']
        
        # Базовый шаблон для будущих кругов (константные фичи: погода, тип шин, grip и т.д.)
        base_lap_dict = last_known_lap.to_dict()
        
        # Итеративно прогнозируем на n кругов вперед
        for step in range(1, n_laps + 1):
            # Создаем запись для нового круга
            future_lap = base_lap_dict.copy()
            
            # Обновляем изменяющиеся со временем параметры
            current_lap_num += 1
            current_tyre_age += 1
            
            future_lap['lap_number'] = current_lap_num
            future_lap['tyre_age'] = current_tyre_age
            
            # Подставляем лаги (из прошлых предсказаний / реальных крайних кругов)
            future_lap['shift_1_lap_time'] = pred_shift_1
            future_lap['shift_2_lap_time'] = pred_shift_2
            
            # Превращаем в DataFrame (1 строка) для модели
            X_step = pd.DataFrame([future_lap])[feature_columns]
            
            # Делаем предикт для текущего шага
            # [0] так как predict возвращает массив/список
            predicted_time = model.predict(X_step)[0] 
            
            # Записываем предсказанное время
            future_lap['lap_time'] = predicted_time
            future_lap['is_predicted_future'] = True  # Флаг, что это сгенерированный круг
            
            future_laps_list.append(future_lap)
            
            # Сдвигаем лаги для следующей итерации (следующего круга)
            pred_shift_2 = pred_shift_1
            pred_shift_1 = predicted_time

    # Превращаем список предсказаний в DataFrame
    df_future = pd.DataFrame(future_laps_list)
    
    # Помечаем исторические данные флагом
    df['is_predicted_future'] = False
    
    # Объединяем историю и прогноз в один красивый датафрейм
    final_df = pd.concat([df, df_future], ignore_index=True)
    final_df = final_df.sort_values(by=['driver_number', 'stint_number', 'lap_number']).reset_index(drop=True)
    
    return final_df[return_columns]