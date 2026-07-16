import type { Spec } from "@json-render/core";
import { JSONUIProvider, Renderer } from "@json-render/ink";
import { Box, Text } from "ink";
import Image from "ink-picture";

import type { SmithUiPayload } from "./smith-ui-schema.js";
import { BORDER, INFO, MUTED } from "./theme.js";

function ImageAttachments({ images }: Pick<SmithUiPayload, "images">) {
  if (images.length === 0) return null;
  return (
    <Box flexDirection="column" marginTop={1}>
      {images.map((image) => (
        <Box key={image.path} flexDirection="column" marginBottom={1}>
          <Image src={image.path} width={image.width} height={image.height} alt={image.alt} />
          <Text color={MUTED}>{image.alt}</Text>
        </Box>
      ))}
    </Box>
  );
}

export function SmithUiBlock({ payload }: { payload: SmithUiPayload }) {
  return (
    <Box borderColor={BORDER} borderStyle="round" flexDirection="column" marginTop={1} paddingX={1}>
      <Text color={INFO} dimColor>
        structured result
      </Text>
      <JSONUIProvider>
        <Renderer spec={payload.spec as Spec} />
      </JSONUIProvider>
      <ImageAttachments images={payload.images} />
    </Box>
  );
}
