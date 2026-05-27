const VERSION_PREFIX = "v";

export function formatVersionLabel(version?: string | null): string {
  if (!version) {
    return "-";
  }

  return version.startsWith(VERSION_PREFIX) ? version : `${VERSION_PREFIX}${version}`;
}

