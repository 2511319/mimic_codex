import type { ComponentType } from "react";

export type FeatureManifest = {
  id: string;
  title: string;
  Component: ComponentType; // для lazy-обёртки поставляем уже ленивый компонент
};

export interface FeatureRegistry {
  register: (manifest: FeatureManifest) => void;
  list: () => FeatureManifest[];
}
