# Use a lightweight Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (needed for some Google auth libs)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirement file first (better Docker caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . .

# Expose the port Cloud Run / Docker will use
ENV PORT=8080
EXPOSE 8080

# Default env so container won't crash if user forgets
ENV SECRET_KEY="dev-secret"
ENV GCP_SA_KEY=""

# Start the app
CMD ["python", "app.py"]
