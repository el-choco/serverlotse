FROM python:3.15.1-alpine3.24
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY server.py scan_index.py toolkit.py recovery.py docker_gateway.py auth.py localization.py admin_demo.py sensors_demo.py advanced_demo.py workbench_demo.py admin_client.py ./
COPY static ./static
EXPOSE 8099
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/health', timeout=2)"
CMD ["python", "server.py"]
