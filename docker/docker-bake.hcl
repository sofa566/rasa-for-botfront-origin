variable "IMAGE_NAME" {
  default = "rasa/rasa"
}

variable "IMAGE_TAG" {
  default = "localdev"
}
variable "GPU_TAG" {
  default = "gpu-"
}

variable "BASE_IMAGE_HASH" {
  default = "localdev"
}

variable "BASE_MITIE_IMAGE_HASH" {
  default = "localdev"
}

variable "BASE_BUILDER_IMAGE_HASH" {
  default = "localdev"
}

# keep this in sync with the version in pyproject.toml
# the variable is set automatically for builds in CI
variable "POETRY_VERSION" {
  default = "1.1.12"
}

group "base-images" {
  targets = ["base", "base-poetry", "base-mitie"]
}

target "base" {
  dockerfile = "docker/Dockerfile.base"
  tags       = ["${IMAGE_NAME}:base-${IMAGE_TAG}"]
  cache-to   = ["type=inline"]
}

target "base-mitie" {
  dockerfile = "docker/Dockerfile.base-mitie"
  tags       = ["${IMAGE_NAME}:base-mitie-${IMAGE_TAG}"]
  cache-to   = ["type=inline"]
}

target "base-poetry" {
  dockerfile = "docker/Dockerfile.base-poetry"
  tags       = ["${IMAGE_NAME}:base-poetry-${POETRY_VERSION}"]

  args = {
    GPU_TAG         = ""
    IMAGE_BASE_NAME = "${IMAGE_NAME}"
    BASE_IMAGE_HASH = "${BASE_IMAGE_HASH}"
    POETRY_VERSION  = "${POETRY_VERSION}"
  }

  cache-to = ["type=inline"]

  cache-from = [
    "type=registry,ref=${IMAGE_NAME}:base-poetry-${POETRY_VERSION}",
  ]
}

target "base-builder" {
  dockerfile = "docker/Dockerfile.base-builder"
  tags       = ["${IMAGE_NAME}:base-builder-${IMAGE_TAG}"]

  args = {
    GPU_TAG         = ""
    IMAGE_BASE_NAME = "${IMAGE_NAME}"
    POETRY_VERSION  = "${POETRY_VERSION}"
  }

  cache-to = ["type=inline"]
}

target "default" {
  dockerfile = "docker/Dockerfile.botfront"
  tags       = ["${IMAGE_NAME}:${IMAGE_TAG}"]

  args = {
    IMAGE_BASE_NAME         = "${IMAGE_NAME}"
    BASE_IMAGE_HASH         = "${BASE_IMAGE_HASH}"
    BASE_BUILDER_IMAGE_HASH = "${BASE_BUILDER_IMAGE_HASH}"
  }

  cache-to = ["type=inline"]

  cache-from = [
    "type=registry,ref=${IMAGE_NAME}:base-${BASE_IMAGE_HASH}",
    "type=registry,ref=${IMAGE_NAME}:base-builder-${BASE_BUILDER_IMAGE_HASH}",
    "type=registry,ref=${IMAGE_NAME}/${IMAGE_NAME}:latest",
  ]
}

target "default-gpu" {
  dockerfile = "docker/Dockerfile.botfront_gpu"
  tags       = ["${IMAGE_NAME}:${IMAGE_TAG}"]

  args = {
    IMAGE_BASE_NAME         = "${IMAGE_NAME}"
    BASE_IMAGE_HASH         = "${BASE_IMAGE_HASH}"
    BASE_BUILDER_IMAGE_HASH = "${BASE_BUILDER_IMAGE_HASH}"
  }

  cache-to = ["type=inline"]

  cache-from = [
    "type=registry,ref=${IMAGE_NAME}:base-${BASE_IMAGE_HASH}",
    "type=registry,ref=${IMAGE_NAME}:base-builder-${BASE_BUILDER_IMAGE_HASH}",
    "type=registry,ref=${IMAGE_NAME}/${IMAGE_NAME}:latest",
  ]
}

target "full" {
  dockerfile = "docker/Dockerfile.full"
  tags       = ["${IMAGE_NAME}:${IMAGE_TAG}-full"]

  args = {
    IMAGE_BASE_NAME         = "${IMAGE_NAME}"
    BASE_IMAGE_HASH         = "${BASE_IMAGE_HASH}"
    BASE_MITIE_IMAGE_HASH   = "${BASE_MITIE_IMAGE_HASH}"
    BASE_BUILDER_IMAGE_HASH = "${BASE_BUILDER_IMAGE_HASH}"
  }

  cache-to = ["type=inline"]

  cache-from = [
    "type=registry,ref=${IMAGE_NAME}:base-${BASE_IMAGE_HASH}",
    "type=registry,ref=${IMAGE_NAME}:base-builder-${BASE_BUILDER_IMAGE_HASH}",
    "type=registry,ref=${IMAGE_NAME}:latest-full",
  ]
}

target "mitie-en" {
  dockerfile = "docker/Dockerfile.pretrained_embeddings_mitie_en"
  tags       = ["${IMAGE_NAME}:${IMAGE_TAG}-mitie-en"]

  args = {
    IMAGE_BASE_NAME         = "${IMAGE_NAME}"
    BASE_IMAGE_HASH         = "${BASE_IMAGE_HASH}"
    BASE_MITIE_IMAGE_HASH   = "${BASE_MITIE_IMAGE_HASH}"
    BASE_BUILDER_IMAGE_HASH = "${BASE_BUILDER_IMAGE_HASH}"
  }

  cache-to = ["type=inline"]

  cache-from = [
    "type=registry,ref=${IMAGE_NAME}:base-${BASE_IMAGE_HASH}",
    "type=registry,ref=${IMAGE_NAME}:base-mitie-${BASE_MITIE_IMAGE_HASH}",
    "type=registry,ref=${IMAGE_NAME}:base-builder-${BASE_BUILDER_IMAGE_HASH}",
    "type=registry,ref=${IMAGE_NAME}:latest-mitie-en",
  ]
}

target "spacy-de" {
  dockerfile = "docker/Dockerfile.pretrained_embeddings_spacy_de"
  tags       = ["${IMAGE_NAME}:${IMAGE_TAG}-spacy-de"]

  args = {
    IMAGE_BASE_NAME         = "${IMAGE_NAME}"
    BASE_IMAGE_HASH         = "${BASE_IMAGE_HASH}"
    BASE_BUILDER_IMAGE_HASH = "${BASE_BUILDER_IMAGE_HASH}"
  }

  cache-to = ["type=inline"]

  cache-from = [
    "type=registry,ref=${IMAGE_NAME}:base-${BASE_IMAGE_HASH}",
    "type=registry,ref=${IMAGE_NAME}:base-builder-${BASE_BUILDER_IMAGE_HASH}",
    "type=registry,ref=${IMAGE_NAME}:latest-spacy-de",
  ]
}

target "spacy-en" {
  dockerfile = "docker/Dockerfile.pretrained_embeddings_spacy_en"
  tags       = ["${IMAGE_NAME}:${IMAGE_TAG}-spacy-en"]

  args = {
    IMAGE_BASE_NAME         = "${IMAGE_NAME}"
    BASE_IMAGE_HASH         = "${BASE_IMAGE_HASH}"
    BASE_BUILDER_IMAGE_HASH = "${BASE_BUILDER_IMAGE_HASH}"
  }

  cache-to = ["type=inline"]

  cache-from = [
    "type=registry,ref=${IMAGE_NAME}:base-${BASE_IMAGE_HASH}",
    "type=registry,ref=${IMAGE_NAME}:base-builder-${BASE_BUILDER_IMAGE_HASH}",
    "type=registry,ref=${IMAGE_NAME}:latest-spacy-en",
  ]
}
target "spacy-zh" {
  dockerfile = "docker/Dockerfile.pretrained_embeddings_spacy_zh"
  tags       = ["${IMAGE_NAME}:${IMAGE_TAG}-spacy-zh"]

  args = {
    GPU_TAG                 = ""
    IMAGE_BASE_NAME         = "${IMAGE_NAME}"
    BASE_IMAGE_HASH         = "${BASE_IMAGE_HASH}"
    BASE_BUILDER_IMAGE_HASH = "${BASE_BUILDER_IMAGE_HASH}"
  }

  cache-to = ["type=inline"]

  cache-from = [
    "type=registry,ref=${IMAGE_NAME}:base-${BASE_IMAGE_HASH}",
    "type=registry,ref=${IMAGE_NAME}:base-builder-${BASE_BUILDER_IMAGE_HASH}",
  ]
}
################################################################

target "base-gpu" {
  dockerfile = "docker/Dockerfile.base-gpu"
  tags       = ["${IMAGE_NAME}:base-${GPU_TAG}${IMAGE_TAG}"]
  cache-to   = ["type=inline"]
}

target "base-gpu-poetry" {
  dockerfile = "docker/Dockerfile.base-poetry"
  tags       = ["${IMAGE_NAME}:base-gpu-poetry-${POETRY_VERSION}"]

  args = {
    GPU_TAG         = "${GPU_TAG}"
    IMAGE_BASE_NAME = "${IMAGE_NAME}"
    BASE_IMAGE_HASH = "${BASE_IMAGE_HASH}"
    POETRY_VERSION  = "${POETRY_VERSION}"
  }

  cache-to = ["type=inline"]

  cache-from = [
    "type=registry,ref=${IMAGE_NAME}:base-${GPU_TAG}${IMAGE_TAG}",
  ]
}
target "base-gpu-builder" {
  dockerfile = "docker/Dockerfile.base-builder"
  tags       = ["${IMAGE_NAME}:base-gpu-builder-${IMAGE_TAG}"]

  args = {
    GPU_TAG         = "${GPU_TAG}"
    IMAGE_BASE_NAME = "${IMAGE_NAME}"
    POETRY_VERSION  = "${POETRY_VERSION}"
  }

  cache-to = ["type=inline"]
}

target "gpu-spacy-zh" {
  dockerfile = "docker/Dockerfile.pretrained_embeddings_spacy_zh"
  tags       = ["${IMAGE_NAME}:${GPU_TAG}${IMAGE_TAG}-spacy-zh"]

  args = {
    GPU_TAG                 = "${GPU_TAG}"
    IMAGE_BASE_NAME         = "${IMAGE_NAME}"
    BASE_IMAGE_HASH         = "${BASE_IMAGE_HASH}"
    BASE_BUILDER_IMAGE_HASH = "${BASE_BUILDER_IMAGE_HASH}"
  }

  cache-to = ["type=inline"]

  cache-from = [
    "type=registry,ref=${IMAGE_NAME}:base-${BASE_IMAGE_HASH}",
    "type=registry,ref=${IMAGE_NAME}:base-builder-${BASE_BUILDER_IMAGE_HASH}",
  ]
}
