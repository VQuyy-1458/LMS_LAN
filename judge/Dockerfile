FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ libc6-dev openjdk-17-jdk-headless python3 coreutils && rm -rf /var/lib/apt/lists/*
ENV LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /work
USER 65534:65534
