FROM python:3.12.3

WORKDIR /app

# Копируем и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Копируем остальной код
COPY . .

# Открываем порт для Streamlit
EXPOSE 8501

# Команда запуска
CMD ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0"]