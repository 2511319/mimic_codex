import type { FeatureManifest } from "../../feature/types";

import PartyFeature from "./view";

const manifest: FeatureManifest = {
  id: "party",
  title: "Party",
  Component: PartyFeature
};

export default manifest;
