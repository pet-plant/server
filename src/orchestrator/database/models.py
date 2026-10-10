from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for PoC database tables."""


class Plant(Base):
    """Plant metadata needed to run assessment without hard-coded context."""

    __tablename__ = "plants"

    plant_id: Mapped[str] = mapped_column(Text, primary_key=True)
    species: Mapped[str] = mapped_column(Text, nullable=False)
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    care_preferences_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    cameras: Mapped[list[Camera]] = relationship(back_populates="plant")


class Camera(Base):
    """Camera registered for a plant."""

    __tablename__ = "cameras"

    camera_id: Mapped[str] = mapped_column(Text, primary_key=True)
    plant_id: Mapped[str] = mapped_column(ForeignKey("plants.plant_id"), nullable=False)
    status: Mapped[bool] = mapped_column(Boolean, nullable=False)

    plant: Mapped[Plant] = relationship(back_populates="cameras")


class Knowledge(Base):
    """Knowledge document path keyed by plant species."""

    __tablename__ = "knowledge"

    knowledge_id: Mapped[str] = mapped_column(String, primary_key=True)
    species: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)


class ImageCapture(Base):
    """Raw camera capture written by the vision pipeline."""

    __tablename__ = "image_captures"

    capture_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.camera_id"), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw_image_uri: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    brightness: Mapped[float | None] = mapped_column(Float, nullable=True)
    blur_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)

    camera: Mapped[Camera] = relationship()
    processed_images: Mapped[list[ProcessedImage]] = relationship(back_populates="capture")


class ProcessedImage(Base):
    """Processed image produced from a raw capture after quality passes."""

    __tablename__ = "processed_images"

    processed_image_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    capture_id: Mapped[int] = mapped_column(ForeignKey("image_captures.capture_id"), nullable=False)
    processed_image_uri: Mapped[str] = mapped_column(Text, nullable=False)
    crop_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    capture: Mapped[ImageCapture] = relationship(back_populates="processed_images")


class Assessment(Base):
    """Assessment summary comparing two processed images from the same plant."""

    __tablename__ = "assessments"

    assessment_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    previous_image_id: Mapped[int] = mapped_column(
        ForeignKey("processed_images.processed_image_id"),
        nullable=False,
    )
    current_image_id: Mapped[int] = mapped_column(
        ForeignKey("processed_images.processed_image_id"),
        nullable=False,
    )
    health_status: Mapped[str] = mapped_column(Text, nullable=False)
    agreement: Mapped[float | None] = mapped_column(Float, nullable=True)
    runs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_stated_average: Mapped[float | None] = mapped_column(Float, nullable=True)

    previous_image: Mapped[ProcessedImage] = relationship(foreign_keys=[previous_image_id])
    current_image: Mapped[ProcessedImage] = relationship(foreign_keys=[current_image_id])
    observation_details: Mapped[list[ObservationDetail]] = relationship(back_populates="assessment")


class ObservationDetail(Base):
    """One observation detail attached to an assessment."""

    __tablename__ = "observation_details"

    observation_detail_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.assessment_id"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    assessment: Mapped[Assessment] = relationship(back_populates="observation_details")
