from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from assessment.run_assessment import AssessmentPipelineError, run_assessment
from capture.run_vision import VisionPipelineError, run_vision

from orchestrator.database.connection import engine, get_db
from orchestrator.database.models import (
    Assessment,
    Base,
    Camera,
    ImageCapture,
    Knowledge,
    ObservationDetail,
    Plant,
    ProcessedImage,
)

app = FastAPI(title="Ambient Pet-Plant Companion API")


EXPECTED_COLUMNS = {
    "cameras": {"camera_id", "plant_id", "status"},
    "plants": {"plant_id", "species", "nickname", "location", "care_preferences_json"},
    "knowledge": {"knowledge_id", "species", "file_path"},
    "image_captures": {
        "capture_id",
        "camera_id",
        "captured_at",
        "raw_image_uri",
        "width",
        "height",
        "brightness",
        "blur_score",
        "quality_passed",
    },
    "processed_images": {
        "processed_image_id",
        "capture_id",
        "processed_image_uri",
        "crop_type",
        "width",
        "height",
        "processed_at",
    },
    "assessments": {
        "assessment_id",
        "previous_image_id",
        "current_image_id",
        "health_status",
        "agreement",
        "runs",
        "model_stated_average",
    },
    "observation_details": {
        "observation_detail_id",
        "assessment_id",
        "type",
        "severity",
        "description",
    },
}


class PlantUpsertRequest(BaseModel):
    plant_id: str = Field(min_length=1)
    species: str = "Spathiphyllum wallisii"
    nickname: str | None = None
    location: str | None = None
    care_preferences_json: str | None = None


class CameraUpsertRequest(BaseModel):
    camera_id: str = Field(min_length=1)
    plant_id: str = Field(min_length=1)
    status: bool = True


class PipelineRunRequest(BaseModel):
    plant_id: str = Field(min_length=1)
    camera_id: str = Field(min_length=1)
    previous_image_path: str | None = None
    fail_on_invalid_quality: bool = True
    run_assessment_after_vision: bool = True
    assessment_runs: int = 1
    assessment_temperature: float = 0.0

class AssessmentOnlyRequest(BaseModel):
    plant_id: str = Field(min_length=1)
    previous_image_id: int = Field(gt=0)
    current_image_id: int = Field(gt=0)
    runs: int = Field(default=1, ge=1)
    temperature: float = 0.0

class PipelineRunResponse(BaseModel):
    ok: bool
    stage: str
    capture_id: int | None = None
    processed_image_id: int | None = None
    assessment_id: int | None = None
    vision: dict[str, Any]
    assessment: dict[str, Any] | None = None


@app.on_event("startup")
def create_tables() -> None:
    """Create PoC tables when migrations are not being used yet."""

    Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return {"message": "Pet-Plant API is running"}


@app.get("/health/db")
def database_health():
    with engine.connect() as connection:
        database = connection.execute(text("SELECT current_database()")).scalar_one()

    return {
        "status": "connected",
        "database": database,
    }


@app.get("/health/schema", response_model=dict[str, Any])
def schema_health(db: Session = Depends(get_db)):
    return {"status": "ok", "tables": assert_database_schema(db)}


@app.post("/plants", response_model=dict[str, Any])
def upsert_plant(request: PlantUpsertRequest, db: Session = Depends(get_db)):
    plant = db.get(Plant, request.plant_id)
    if plant is None:
        plant = Plant(plant_id=request.plant_id)
        db.add(plant)

    plant.species = request.species
    plant.nickname = request.nickname
    plant.location = request.location
    plant.care_preferences_json = request.care_preferences_json
    db.commit()
    db.refresh(plant)
    return plant_to_dict(plant)


@app.get("/plants/{plant_id}", response_model=dict[str, Any])
def get_plant(plant_id: str, db: Session = Depends(get_db)):
    plant = db.get(Plant, plant_id)
    if plant is None:
        raise HTTPException(status_code=404, detail=f"Plant not found: {plant_id}")
    return plant_to_dict(plant)


@app.post("/cameras", response_model=dict[str, Any])
def upsert_camera(request: CameraUpsertRequest, db: Session = Depends(get_db)):
    plant = db.get(Plant, request.plant_id)
    if plant is None:
        raise HTTPException(status_code=404, detail=f"Plant not found: {request.plant_id}")

    camera = db.get(Camera, request.camera_id)
    if camera is None:
        camera = Camera(camera_id=request.camera_id, plant_id=request.plant_id)
        db.add(camera)

    camera.plant_id = request.plant_id
    camera.status = request.status
    db.commit()
    db.refresh(camera)
    return camera_to_dict(camera)


@app.get("/plants/{plant_id}/latest", response_model=dict[str, Any])
def get_latest_pipeline_results(plant_id: str, db: Session = Depends(get_db)):
    plant = db.get(Plant, plant_id)
    if plant is None:
        raise HTTPException(status_code=404, detail=f"Plant not found: {plant_id}")

    latest_processed = get_previous_processed_image(db, plant_id)
    latest_assessment = db.scalars(
        select(Assessment)
        .join(ProcessedImage, Assessment.current_image_id == ProcessedImage.processed_image_id)
        .join(ImageCapture, ProcessedImage.capture_id == ImageCapture.capture_id)
        .join(Camera, ImageCapture.camera_id == Camera.camera_id)
        .where(Camera.plant_id == plant_id)
        .order_by(Assessment.assessment_id.desc())
        .limit(1)
    ).first()

    return {
        "plant": plant_to_dict(plant),
        "latest_vision": (
            processed_image_to_dict(latest_processed) if latest_processed else None
        ),
        "latest_assessment": (
            assessment_to_dict(latest_assessment) if latest_assessment else None
        ),
    }

@app.post("/assessment/run", response_model=dict[str, Any])
def run_assessment_only(
    request: AssessmentOnlyRequest,
    db: Session = Depends(get_db),
):
    assert_database_schema(db)

    # 1. Validate plant
    plant = db.get(Plant, request.plant_id)

    if plant is None:
        raise HTTPException(
            status_code=404,
            detail=f"Plant not found: {request.plant_id}",
        )

    # 2. Previous and current images must be different
    if request.previous_image_id == request.current_image_id:
        raise HTTPException(
            status_code=400,
            detail="Previous and current images must be different.",
        )

    # 3. Query processed images belonging to this plant
    def find_plant_image(image_id: int) -> ProcessedImage | None:
        return db.scalars(
            select(ProcessedImage)
            .join(
                ImageCapture,
                ProcessedImage.capture_id == ImageCapture.capture_id,
            )
            .join(
                Camera,
                ImageCapture.camera_id == Camera.camera_id,
            )
            .where(
                ProcessedImage.processed_image_id == image_id,
                Camera.plant_id == plant.plant_id,
            )
            .limit(1)
        ).first()

    previous_image = find_plant_image(request.previous_image_id)
    current_image = find_plant_image(request.current_image_id)

    if previous_image is None:
        raise HTTPException(
            status_code=404,
            detail="Previous processed image not found for this plant.",
        )

    if current_image is None:
        raise HTTPException(
            status_code=404,
            detail="Current processed image not found for this plant.",
        )

    # 4. Validate chronological order
    # IDs are used here because the existing pipeline retrieves
    # the latest processed image by descending processed_image_id.
    if previous_image.processed_image_id >= current_image.processed_image_id:
        raise HTTPException(
            status_code=400,
            detail="Previous image must be older than current image.",
        )

    # 5. Load knowledge from database
    knowledge = get_knowledge_for_plant(db, plant)

    # 6. Run Assessment Pipeline (without running Vision)
    try:
        assessment_result = run_assessment(
            previous_image_path=previous_image.processed_image_uri,
            current_image_path=current_image.processed_image_uri,
            plant_context={
                "plant_id": plant.plant_id,
                "species": plant.species,
                "knowledge_file": knowledge.file_path,
            },
            runs=request.runs,
            temperature=request.temperature,
        )

        # 7. Validate Assessment output
        assert_assessment_output(assessment_result)

        # 8. Map result to assessments table
        assessment = assessment_from_result(
            previous_image.processed_image_id,
            current_image.processed_image_id,
            assessment_result,
        )

        db.add(assessment)
        db.flush()

        # 9. Map observations to observation_details table
        observation_details = observation_details_from_result(
            assessment.assessment_id,
            assessment_result,
        )

        for detail in observation_details:
            db.add(detail)

        # 10. Commit all assessment records
        db.commit()

    except HTTPException:
        db.rollback()
        raise

    except AssessmentPipelineError as error:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

    except Exception:
        db.rollback()
        raise

    # 11. Return assessment result
    return {
        "ok": True,
        "stage": "assessment_completed",
        "plant_id": plant.plant_id,
        "previous_image_id": previous_image.processed_image_id,
        "current_image_id": current_image.processed_image_id,
        "assessment_id": assessment.assessment_id,
        "observation_count": len(observation_details),
        "assessment": assessment_result,
    }


@app.post("/pipeline/run", response_model=PipelineRunResponse)
def run_pipeline(request: PipelineRunRequest, db: Session = Depends(get_db)):
    assert_database_schema(db)

    plant = db.get(Plant, request.plant_id)
    if plant is None:
        raise HTTPException(status_code=404, detail=f"Plant not found: {request.plant_id}")

    camera = db.get(Camera, request.camera_id)
    if camera is None or camera.plant_id != plant.plant_id:
        raise HTTPException(status_code=404, detail=f"Camera not found for plant: {request.camera_id}")
    if not camera.status:
        raise HTTPException(status_code=400, detail=f"Camera is inactive: {request.camera_id}")

    previous_image = resolve_previous_processed_image(
        db,
        plant.plant_id,
        request.previous_image_path,
    )

    try:
        vision_result = run_vision(
            local_camera_id_for(camera.camera_id),
            plant_id=plant.plant_id,
            fail_on_invalid_quality=request.fail_on_invalid_quality,
        )
    except VisionPipelineError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    assert_vision_output(vision_result)
    image_capture = image_capture_from_vision(camera.camera_id, vision_result)
    db.add(image_capture)
    db.flush()

    if not vision_result.get("ok"):
        db.commit()
        return PipelineRunResponse(
            ok=False,
            stage=str(vision_result.get("stage", "unknown")),
            capture_id=image_capture.capture_id,
            vision=vision_result,
        )

    processed_image = processed_image_from_vision(image_capture.capture_id, vision_result)
    db.add(processed_image)
    db.flush()

    if not request.run_assessment_after_vision:
        db.commit()
        return PipelineRunResponse(
            ok=True,
            stage="vision_completed",
            capture_id=image_capture.capture_id,
            processed_image_id=processed_image.processed_image_id,
            vision=vision_result,
        )

    if previous_image is None:
        db.commit()
        return PipelineRunResponse(
            ok=True,
            stage="vision_completed_no_previous_image",
            capture_id=image_capture.capture_id,
            processed_image_id=processed_image.processed_image_id,
            vision=vision_result,
        )

    knowledge = get_knowledge_for_plant(db, plant)
    try:
        assessment_result = run_assessment(
            previous_image_path=previous_image.processed_image_uri,
            current_image_path=processed_image.processed_image_uri,
            plant_context={
                "plant_id": plant.plant_id,
                "species": plant.species,
                "knowledge_file": knowledge.file_path,
            },
            runs=request.assessment_runs,
            temperature=request.assessment_temperature,
        )
    except AssessmentPipelineError as error:
        db.commit()
        raise HTTPException(status_code=500, detail=str(error)) from error

    assert_assessment_output(assessment_result)
    assessment = assessment_from_result(
        previous_image.processed_image_id,
        processed_image.processed_image_id,
        assessment_result,
    )
    db.add(assessment)
    db.flush()

    for detail in observation_details_from_result(assessment.assessment_id, assessment_result):
        db.add(detail)

    db.commit()

    return PipelineRunResponse(
        ok=True,
        stage="completed",
        capture_id=image_capture.capture_id,
        processed_image_id=processed_image.processed_image_id,
        assessment_id=assessment.assessment_id,
        vision=vision_result,
        assessment=assessment_result,
    )


def assert_database_schema(db: Session) -> dict[str, list[str]]:
    inspector = inspect(db.bind)
    checked: dict[str, list[str]] = {}
    for table_name, required_columns in EXPECTED_COLUMNS.items():
        if not inspector.has_table(table_name):
            raise HTTPException(status_code=500, detail=f"Missing table: {table_name}")

        actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
        missing_columns = sorted(required_columns - actual_columns)
        if missing_columns:
            raise HTTPException(
                status_code=500,
                detail=f"Table {table_name} is missing columns: {', '.join(missing_columns)}",
            )
        checked[table_name] = sorted(required_columns)
    return checked


def assert_vision_output(vision_result: dict[str, Any]) -> None:
    capture = vision_result.get("capture")
    quality = vision_result.get("quality")
    if not isinstance(capture, dict):
        raise HTTPException(status_code=500, detail="Vision output is missing capture metadata.")
    if not isinstance(quality, dict):
        raise HTTPException(status_code=500, detail="Vision output is missing quality metadata.")
    if not capture.get("image_path"):
        raise HTTPException(status_code=500, detail="Vision output is missing raw image path.")

    if vision_result.get("ok"):
        processed = vision_result.get("processed")
        if not isinstance(processed, dict) or not processed.get("processed_image_path"):
            raise HTTPException(status_code=500, detail="Vision output is missing processed image path.")


def assert_assessment_output(assessment_result: dict[str, Any]) -> None:
    if not assessment_result.get("health_status"):
        raise HTTPException(status_code=500, detail="Assessment output is missing health_status.")
    consensus = assessment_result.get("consensus")
    if not isinstance(consensus, dict):
        raise HTTPException(status_code=500, detail="Assessment output is missing consensus.")
    observations = assessment_result.get("observations")
    if observations is not None and not isinstance(observations, list):
        raise HTTPException(status_code=500, detail="Assessment observations must be a list.")


def plant_to_dict(plant: Plant) -> dict[str, Any]:
    return {
        "plant_id": plant.plant_id,
        "species": plant.species,
        "nickname": plant.nickname,
        "location": plant.location,
        "care_preferences_json": plant.care_preferences_json,
    }


def camera_to_dict(camera: Camera) -> dict[str, Any]:
    return {
        "camera_id": camera.camera_id,
        "plant_id": camera.plant_id,
        "status": camera.status,
    }


def local_camera_id_for(camera_id: str) -> str:
    """Map DB camera IDs to local capture IDs used by run_vision."""

    return {"camera_001": "webcam_0"}.get(camera_id, camera_id)


def resolve_previous_processed_image(
    db: Session,
    plant_id: str,
    previous_image_path: str | None,
) -> ProcessedImage | None:
    if previous_image_path:
        previous_image = get_processed_image_for_plant(db, plant_id, previous_image_path)
        if previous_image is None:
            raise HTTPException(
                status_code=404,
                detail="Previous processed image was not found for this plant.",
            )
        return previous_image
    return get_previous_processed_image(db, plant_id)


def get_previous_processed_image(db: Session, plant_id: str) -> ProcessedImage | None:
    return db.scalars(
        select(ProcessedImage)
        .join(ImageCapture, ProcessedImage.capture_id == ImageCapture.capture_id)
        .join(Camera, ImageCapture.camera_id == Camera.camera_id)
        .where(Camera.plant_id == plant_id)
        .order_by(ProcessedImage.processed_image_id.desc())
        .limit(1)
    ).first()


def get_processed_image_for_plant(
    db: Session,
    plant_id: str,
    processed_image_uri: str,
) -> ProcessedImage | None:
    return db.scalars(
        select(ProcessedImage)
        .join(ImageCapture, ProcessedImage.capture_id == ImageCapture.capture_id)
        .join(Camera, ImageCapture.camera_id == Camera.camera_id)
        .where(
            Camera.plant_id == plant_id,
            ProcessedImage.processed_image_uri == processed_image_uri,
        )
        .limit(1)
    ).first()


def get_knowledge_for_plant(db: Session, plant: Plant) -> Knowledge:
    knowledge = db.scalars(
        select(Knowledge)
        .join(Plant, Plant.species == Knowledge.species)
        .where(Plant.plant_id == plant.plant_id)
        .limit(1)
    ).first()
    if knowledge is None:
        raise HTTPException(
            status_code=404,
            detail=f"Knowledge not found for species: {plant.species}",
        )
    return knowledge


def parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def image_capture_from_vision(camera_id: str, vision_result: dict[str, Any]) -> ImageCapture:
    capture = vision_result["capture"]
    quality = vision_result["quality"]
    captured_at = parse_datetime(capture.get("captured_at"))
    values: dict[str, Any] = {
        "camera_id": camera_id,
        "raw_image_uri": str(capture["image_path"]),
        "width": int(quality.get("width") or capture.get("width") or 0),
        "height": int(quality.get("height") or capture.get("height") or 0),
        "brightness": float(quality["brightness"]) if quality.get("brightness") is not None else None,
        "blur_score": float(quality["blur_score"]) if quality.get("blur_score") is not None else None,
        "quality_passed": bool(quality.get("valid")),
    }
    if captured_at is not None:
        values["captured_at"] = captured_at
    return ImageCapture(**values)


def processed_image_from_vision(capture_id: int, vision_result: dict[str, Any]) -> ProcessedImage:
    processed = vision_result["processed"]
    return ProcessedImage(
        capture_id=capture_id,
        processed_image_uri=str(processed["processed_image_path"]),
        crop_type=processed.get("crop_type"),
        width=int(processed["output_width"]) if processed.get("output_width") is not None else None,
        height=int(processed["output_height"]) if processed.get("output_height") is not None else None,
    )


def assessment_from_result(
    previous_image_id: int,
    current_image_id: int,
    assessment_result: dict[str, Any],
) -> Assessment:
    consensus = assessment_result["consensus"]
    return Assessment(
        previous_image_id=previous_image_id,
        current_image_id=current_image_id,
        health_status=str(assessment_result["health_status"]),
        agreement=optional_float(consensus.get("agreement")),
        runs=optional_int(consensus.get("runs")),
        model_stated_average=optional_float(consensus.get("model_stated_average")),
    )

def severity_to_str(value: object) -> str | None:
    if isinstance(value, bool) or value is None:
        return None

    if isinstance(value, int):
        return {
            1: "mild",
            2: "moderate",
            3: "severe",
        }.get(value)

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"mild", "moderate", "severe"}:
            return normalized

    return None


def observation_details_from_result(
    assessment_id: int,
    assessment_result: dict[str, Any],
) -> list[ObservationDetail]:
    details = []
    for observation in assessment_result.get("observations") or []:
        if not isinstance(observation, dict):
            continue
        details.append(
            ObservationDetail(
                assessment_id=assessment_id,
                type=str(observation.get("type", "other")),
                severity=severity_to_str(observation.get("severity")),
                description=(
                    str(observation["description"])
                    if observation.get("description") is not None
                    else None
                ),
            )
        )
    return details

def optional_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def optional_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def processed_image_to_dict(processed_image: ProcessedImage) -> dict[str, Any]:
    return {
        "processed_image_id": processed_image.processed_image_id,
        "capture_id": processed_image.capture_id,
        "processed_image_uri": processed_image.processed_image_uri,
        "crop_type": processed_image.crop_type,
        "width": processed_image.width,
        "height": processed_image.height,
        "processed_at": processed_image.processed_at,
    }


def assessment_to_dict(assessment: Assessment) -> dict[str, Any]:
    return {
        "assessment_id": assessment.assessment_id,
        "previous_image_id": assessment.previous_image_id,
        "current_image_id": assessment.current_image_id,
        "health_status": assessment.health_status,
        "agreement": assessment.agreement,
        "runs": assessment.runs,
        "model_stated_average": assessment.model_stated_average,
    }
