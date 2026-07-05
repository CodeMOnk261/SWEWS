# Multi-stage builder stage
FROM python:3.11-slim AS builder

WORKDIR /app

# Install compilation tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy python dependencies
COPY requirements.txt .

# Install dependencies (defaulting to CPU-only PyTorch for lightweight serving)
# For GPU-enabled deployments, remove the --extra-index-url option.
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

# Final runner stage
FROM python:3.11-slim AS runner

WORKDIR /app

# Copy site-packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Create directories for dynamic NOAA cache and outputs
RUN mkdir -p datasets/raw datasets/processed outputs/full_training

# Copy codebase
COPY src/ ./src/
COPY config/ ./config/

# Production environment configurations
# Pinned thread limits eliminate OMP/MKL thread contention bottlenecks
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    VECLIB_MAXIMUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1

# Expose FastAPI default port
EXPOSE 8000

# Run FastAPI app with Uvicorn
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
