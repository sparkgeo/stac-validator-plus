from fastapi import FastAPI

app = FastAPI(title="STAC Validator Plus API")


@app.get("/")
def read_root():
    return {"message": "Welcome to STAC Validator Plus API"}
