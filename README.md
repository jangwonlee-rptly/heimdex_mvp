# Heimdex Metadata API

Heimdex is a FastAPI application that provides a minimal ingest endpoint for extracting media metadata using ffprobe.

## Project Overview

The primary goal of this project is to offer a simple and efficient way to upload media files and receive detailed metadata in a structured format. The API is designed to be used as a microservice in a larger media processing pipeline.

## Setup and Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/heimdex.git
   cd heimdex
   ```

2. **Build and run the Docker container:**
   ```bash
   docker-compose up --build
   ```

## Running the Application

The application will be available at `http://localhost:8000`. You can access the API documentation at `http://localhost:8000/docs`.

## API Endpoints

### `POST /metadata`

Accepts a video upload and returns structured metadata.

- **Request:**
  - `file`: The video file to be uploaded.
- **Response:**
  - `MetadataResponse`: A JSON object containing the extracted metadata.

### `GET /health`

A simple liveness probe.

- **Response:**
  - `HealthResponse`: A JSON object indicating the service is healthy.

## Command-Line Interface (CLI)

The project includes a CLI for developers.

- **Usage:**
  - `python -m app.cli --help`
