import Ajv2020 from 'ajv/dist/2020.js';
import schema from './generated/contracts.json';
import type { CorpusResponse, ErrorResponse, HealthResponse, QuestionResponse } from './types';

const validator = new Ajv2020({ strict: false, validateFormats: false });
validator.addSchema(schema);

function contract<T>(name: keyof typeof schema.$defs) {
  return validator.compile<T>({ $ref: `${schema.$id}#/$defs/${name}` });
}

export const isQuestionResponse = contract<QuestionResponse>('QuestionResponse');
export const isErrorResponse = contract<ErrorResponse>('ErrorResponse');
export const isCorpusResponse = contract<CorpusResponse>('CorpusResponse');
export const isHealthResponse = contract<HealthResponse>('HealthResponse');
export const QUERY_MAX_LENGTH = schema.$defs.QuestionRequest.properties.query.maxLength;
