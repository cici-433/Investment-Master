# Base image with Playwright dependencies (using a community image that has python + browsers)
# Official playwright image is good but large.
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /app

# Copy requirements first
COPY requirements.txt .

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install browsers for playwright
RUN playwright install chromium
RUN playwright install-deps

# Copy application code
COPY . .

# Expose port
EXPOSE 5000

# Run the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
