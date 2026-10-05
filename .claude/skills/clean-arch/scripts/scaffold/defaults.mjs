export const SHAPES = {
  backend: "backend",
  backendNext: "backend-n-nextjs",
};

export function defaultsFor(parsed) {
  return parsed.yes ? yesDefaults() : wizardDefaults();
}

function yesDefaults() {
  return {
    shape: SHAPES.backend,
    db: false,
    install: true,
    gates: true,
    git: true,
  };
}

function wizardDefaults() {
  return {
    shape: SHAPES.backend,
    db: true,
    install: true,
    gates: true,
    git: true,
  };
}
