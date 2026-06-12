# Start with a lightweight, secure Python environment
FROM python:3.10-slim

# Set the working directory inside the container
WORKDIR /app

# Copy all the files from your local folder into the container
COPY . /app

# Install the necessary libraries
RUN pip install --no-cache-dir streamlit pandas numpy plotly sqlalchemy yfinance

# Expose the port Streamlit uses
EXPOSE 8501

# Command to run the application when the container starts
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]