from __future__ import annotations

from pathlib import Path

import pytest

from app.api.routes import kernel_envs as route


class FakeKernelSpecManager:
    def get_all_specs(self):
        return {
            "missing": {
                "spec": {
                    "display_name": "Missing Python",
                    "language": "python",
                    "argv": ["/tmp/aiasys-missing-python", "-m", "ipykernel_launcher"],
                }
            },
            "relative": {
                "spec": {
                    "display_name": "Relative Python",
                    "language": "python",
                    "argv": ["python", "-m", "ipykernel_launcher"],
                }
            },
            "valid": {
                "spec": {
                    "display_name": "Valid Python",
                    "language": "python",
                    "argv": [str(Path(__file__).resolve()), "-m", "ipykernel_launcher"],
                }
            },
        }


@pytest.mark.asyncio
async def test_list_kernel_envs_marks_missing_executables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(route, "_get_kernel_specs", FakeKernelSpecManager().get_all_specs)

    response = await route.list_kernel_envs(current_user=None)  # type: ignore[arg-type]

    kernels = {item["name"]: item for item in response["kernels"]}
    assert kernels["valid"]["executable_exists"] is True
    assert "missing" not in kernels
    assert "relative" not in kernels
