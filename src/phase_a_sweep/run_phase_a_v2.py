"""Run the frozen Phase-A v2 primary sweep with 20 vectors."""

from src.phase_a_sweep.sweep_orchestrator import main


if __name__ == "__main__":
    main(output_dir="outputs/phase_a_v2", limit_vectors=20)
