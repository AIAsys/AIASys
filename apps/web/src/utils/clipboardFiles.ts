function dedupeFiles(files: File[]): File[] {
  return files.filter((file, index, array) => {
    return (
      array.findIndex(
        (candidate) =>
          candidate.name === file.name &&
          candidate.size === file.size &&
          candidate.type === file.type,
      ) === index
    );
  });
}

export function extractClipboardFiles(
  clipboardData: Pick<DataTransfer, "files" | "items"> | null | undefined,
): File[] {
  if (!clipboardData) {
    return [];
  }

  const clipboardFiles = Array.from(clipboardData.files ?? []);
  const itemFiles = Array.from(clipboardData.items ?? [])
    .filter((item) => item.kind === "file")
    .map((item) => item.getAsFile())
    .filter((file): file is File => Boolean(file));

  return dedupeFiles([...clipboardFiles, ...itemFiles]);
}
