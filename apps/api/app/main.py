from fastapi import FastAPI

app = FastAPI(title="AutoResilience API")


@app.get("/health")
def health_check():
    return {"status": "ok"}