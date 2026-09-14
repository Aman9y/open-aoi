"""Application configuration.

All tunable values (paths, quality thresholds, alignment and decision tolerances)
live here and are overridable via environment variables or a ``.env`` file.
Nothing in the inspection engine hard-codes these numbers.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = two levels up from this file (backend/app/config.py -> repo/)
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AOI_",
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- paths -------------------------------------------------------------
    data_dir: Path = REPO_ROOT / "data"
    outputs_dir: Path = REPO_ROOT / "outputs"
    db_path: Path = REPO_ROOT / "data" / "db" / "inspection.sqlite"

    # ---- image preprocessing --------------------------------------------------
    image_max_dim: int = 1280  # longest side after resize

    # ---- image quality gate (stage B) --------------------------------------
    # variance of the Laplacian; below this the image is considered blurred
    # NOTE: calibrate these to your camera + lighting during setup.
    quality_blur_min: float = 20.0
    quality_brightness_min: float = 35.0   # mean grey level (0-255)
    quality_brightness_max: float = 230.0
    quality_contrast_min: float = 14.0     # std dev of grey levels
    quality_overexposed_max_frac: float = 0.12  # fraction of pixels >= 250

    # ---- board detection / cropping (stage A) ----------------------------
    # Real photos: the board does not fill the frame and sits on a cluttered
    # background. Detect the largest board-like quadrilateral and rectify it
    # before alignment. Disable if your fixture already frames the board tightly.
    detect_enabled: bool = True
    detect_min_area_frac: float = 0.10    # board must cover >= this fraction of frame
    detect_max_area_frac: float = 0.985   # above this we assume board already fills frame
    detect_canny_sigma: float = 0.33      # auto Canny thresholds around the median
    detect_pad_frac: float = 0.01         # keep a thin margin around the detected quad
    detect_aspect_tolerance: float = 0.35 # reject quads whose aspect is far from reference

    # ---- alignment (stage C) ---------------------------------------------------
    align_orb_features: int = 6000
    align_lowe_ratio: float = 0.78
    align_min_inliers: int = 22
    align_ransac_reproj_px: float = 4.0
    align_max_error_px: float = 4.0        # median inlier reprojection error
    align_max_rotation_deg: float = 15.0   # sanity clamp on estimated transform
    # After stage-A crop the board can be at any scale vs the reference, so this
    # clamp is loose — reprojection error + board SSIM are the real quality gates.
    align_max_scale_dev: float = 0.7       # |scale - 1| sanity clamp
    align_ecc_fallback: bool = True        # try ECC refinement when ORB is weak

    # ---- per-region comparison defaults (stage D/E/F) ---------------------
    # Overridable per region in the profile's regions.json.
    region_search_margin_px: int = 18     # template-match search halo around region
    region_missing_corr: float = 0.45     # peak NCC below this => MISSING
    region_position_tol_px: float = 8.0
    region_rotation_tol_deg: float = 8.0
    region_ssim_anomaly: float = 0.55     # SSIM below this => strong visual anomaly
    region_ssim_review: float = 0.72      # SSIM in (anomaly, review) => borderline
    region_color_delta_max: float = 38.0  # CIELAB mean-colour drift beyond this => anomaly
                                          # (photo lighting/vignette alone moves small
                                          #  bright regions ~20-30; a wrong colour is 60+)
    # Visual-anomaly / colour checks are only trustworthy on a well-registered
    # board. Below this whole-board SSIM they are suppressed unless the colour
    # change is blatant — a marginal registration goes to REVIEW instead.
    region_anomaly_min_board_ssim: float = 0.80

    # ---- surface inspection mode (whole-object clean vs damaged) ----------
    # Primary signal is windowed SSIM (tolerant of the small placement shift a
    # hand-placed part has). diff-fraction only corroborates / colours the text.
    # Calibrate these from your own clean vs damaged scores (shown in the result
    # panel). Set both to the midpoint for a clean GOOD/DEFECTIVE split.
    surface_defect_ssim: float = 0.55        # below => DEFECTIVE
    surface_review_ssim: float = 0.63        # between => REVIEW; above => GOOD
    surface_diff_threshold: int = 45         # per-pixel abs-diff counted as "different"

    # ---- decision engine -------------------------------------------------------
    decision_min_confidence: float = 0.60  # overall confidence below => REVIEW
    # If alignment claims success but the aligned board's whole-frame SSIM vs the
    # reference is below this AND most regions read as missing, treat the
    # registration as untrustworthy => REVIEW (never DEFECTIVE / GOOD).
    decision_min_board_ssim: float = 0.62

    # ---- pixel -> millimetre calibration (optional) -----------------------
    # If a profile does not define its own, this global value is used for
    # reporting deviations in mm. 0 disables mm reporting.
    mm_per_px: float = 0.0

    # ---- server -----------------------------------------------------------
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # ---- physical station (ESP32 over Wi-Fi) -------------------------------
    # The ESP32 POSTs /api/station/trigger on a button/sensor and polls
    # /api/station/state to drive its LEDs / servo / buzzer. All inert unless
    # station_enabled is true.
    station_enabled: bool = False
    station_source: str = ""              # single-camera trigger capture (index or stream URL)
    # OR multi-camera: a JSON list of {name, source, reference_id?}. When set, the
    # trigger inspects the object from every view at once (verdict = worst view).
    station_views: list[dict] = Field(default_factory=list)
    station_reference_id: str | None = None   # None => the active reference
    station_reject_statuses: list[str] = Field(default_factory=lambda: ["DEFECTIVE"])
    station_esp32_offline_after_s: float = 6.0  # no poll within this => "disconnected"

    # ---- optional ML (milestone 3) ------------------------------------------
    # If unset -> "MODEL NOT CONFIGURED"; the deterministic pipeline is unaffected.
    yolo_model_path: Path | None = None
    yolo_confidence: float = 0.35
    yolo_match_iou: float = 0.10          # min IoU / containment to bind a detection to a region
    yolo_flag_unexpected: bool = False    # emit UNEXPECTED_COMPONENT for stray detections
    # Normalize detector class names to the vocabulary used in regions.json.
    yolo_class_aliases: dict[str, str] = Field(
        default_factory=lambda: {
            "r": "resistor", "res": "resistor", "resistor": "resistor",
            "c": "cap", "cap": "cap", "capacitor": "cap",
            "u": "ic", "ic": "ic", "chip": "ic", "qfp": "ic", "soic": "ic",
            "d": "led", "led": "led", "diode": "led",
            "j": "connector", "conn": "connector", "connector": "connector",
            "header": "connector", "pin_header": "connector",
        }
    )

    @property
    def references_dir(self) -> Path:
        return self.data_dir / "references"

    def ensure_dirs(self) -> None:
        for p in (
            self.data_dir,
            self.references_dir,
            self.data_dir / "test",
            self.data_dir / "samples",
            self.outputs_dir,
            self.db_path.parent,
        ):
            p.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
