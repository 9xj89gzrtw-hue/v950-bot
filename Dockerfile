FROM python:3.12-slim
WORKDIR /app
COPY v948_pullbot.py .
EXPOSE 10000
CMD ["python", "v948_pullbot.py"]
