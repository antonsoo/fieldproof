// Run the real review flow against a separately launched installed wheel.
import config from '../row-association/browser.config.mjs';

export default {
  ...config,
  grep: /a negated extracted date remains reviewable/,
};
