import { queryLength, validateQuery } from './validation';
import { QUERY_MAX_LENGTH } from '../../api/contracts';

it('trims blank questions and enforces the backend boundary', () => {
  expect(validateQuery(' \n ')).toBeDefined();
  expect(validateQuery('a'.repeat(QUERY_MAX_LENGTH))).toBeUndefined();
  expect(validateQuery('a'.repeat(QUERY_MAX_LENGTH + 1))).toBeDefined();
});

it('counts supplementary Unicode characters like the Python API', () => {
  expect(queryLength('  📚⚖️  ')).toBe(3);
  expect(validateQuery('📚'.repeat(QUERY_MAX_LENGTH))).toBeUndefined();
});
