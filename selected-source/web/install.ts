/** The CLI installer is served by this same site (built into the Docker image). Keep WHEEL in step
 * with the version in pyproject.toml; tests/contract/test_contracts.py checks it. */
export const WHEEL = "faultsage-0.1.0-py3-none-any.whl";

export function installUrl(): string {
  return `${window.location.origin}/download/${WHEEL}`;
}
