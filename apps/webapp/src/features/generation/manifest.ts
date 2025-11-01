import type { FeatureManifest } from "../../feature/types";

import GenerationView from "./view";

const manifest: FeatureManifest = {
  id: "generation",
  title: "Generation",
  Component: GenerationView
};

export default manifest;
