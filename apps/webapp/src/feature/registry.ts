import generationManifest from "../features/generation/manifest";
import mediaManifest from "../features/media/manifest";
import partyManifest from "../features/party/manifest";

import type { FeatureManifest, FeatureRegistry } from "./types";

class SimpleRegistry implements FeatureRegistry {
  private manifests: FeatureManifest[] = [];

  constructor(initialManifests: FeatureManifest[]) {
    this.manifests = initialManifests.slice();
  }

  register(manifest: FeatureManifest): void {
    this.manifests.push(manifest);
  }

  list(): FeatureManifest[] {
    return this.manifests.slice();
  }
}

export const registry: FeatureRegistry = new SimpleRegistry([partyManifest, mediaManifest, generationManifest]);
