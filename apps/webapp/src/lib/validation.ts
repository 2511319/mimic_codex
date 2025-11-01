import Ajv, { type ErrorObject } from "ajv/dist/2020";
import addFormats from "ajv-formats";

type ValidationResult = { valid: true } | { valid: false; errors: ErrorObject[] };

// Local copies of JSON Schemas used on FE (canonical versions live under contracts/).
const eventEnvelopeSchema = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  $id: "https://rpg-bot.example/contracts/events/event_envelope.schema.json",
  title: "EventEnvelope",
  type: "object",
  required: ["eventType", "payload"],
  properties: {
    eventType: { type: "string", minLength: 1 },
    payload: {},
    traceId: { type: ["string", "null"] },
    senderId: { type: ["string", "null"] }
  },
  additionalProperties: false
} as const;

const mediaJobResponseSchema = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  $id: "https://rpg-bot.example/contracts/jsonschema/media_job_response.schema.json",
  title: "MediaJobResponse",
  type: "object",
  required: ["jobId", "jobType", "status", "createdAt", "updatedAt"],
  properties: {
    jobId: { type: "string", minLength: 1 },
    jobType: { type: "string", enum: ["tts", "stt", "image", "avatar"] },
    status: { type: "string", enum: ["queued", "processing", "succeeded", "failed"] },
    result: { type: ["object", "null"] },
    error: { type: ["string", "null"] },
    createdAt: { type: "string", format: "date-time" },
    updatedAt: { type: "string", format: "date-time" },
    clientToken: { type: ["string", "null"] }
  },
  additionalProperties: false
} as const;

const ajv = new Ajv({ allErrors: true, strict: false });
addFormats(ajv);
const validateEnvelope = ajv.compile(eventEnvelopeSchema);
const validateMediaJob = ajv.compile(mediaJobResponseSchema);

export function validateEventEnvelope(data: unknown): ValidationResult {
  const ok = validateEnvelope(data);
  if (ok) return { valid: true };
  return { valid: false, errors: (validateEnvelope.errors ?? []) as ErrorObject[] };
}

export function validateMediaJobResponse(data: unknown): ValidationResult {
  const ok = validateMediaJob(data);
  if (ok) return { valid: true };
  return { valid: false, errors: (validateMediaJob.errors ?? []) as ErrorObject[] };
}
