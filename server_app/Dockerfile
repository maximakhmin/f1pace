FROM python:3.12.3

WORKDIR /app

# Копируем и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Копируем остальной код
COPY . .

# Команда запуска обычного Python-файла
CMD ["python", "main.py"]