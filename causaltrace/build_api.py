from fastapi import APIRouter, HTTPException

from causaltrace.build_doctor import (
    BuildRequest,
    demos,
    investigate,
    verify,
)


router = APIRouter(prefix="/api/build")


@router.get("/demos")
def get_demos():
    return {"demos": demos()}


@router.post("/analyze")
def analyze(request: BuildRequest):
    try:
        return investigate(request)

    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error

    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=(
                "Nemotron request failed. Check model access, "
                "credit, and connection."
            ),
        ) from error


@router.post("/{report_id}/verify")
def verify_build(report_id: str):
    try:
        return verify(report_id)

    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except BlockingIOError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        ) from error