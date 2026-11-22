// The OAuth grants the client sends to igni server's token endpoint.

export const ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer";
export const TOKEN_EXCHANGE = "urn:ietf:params:oauth:grant-type:token-exchange";
export const ACCESS_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token";
export const API_KEY_GRANT = "urn:igni:params:oauth:grant-type:api-key";

/** A person's API key, for a short session as them. */
export function apiKeyGrant(apiKey: string): Record<string, string> {
  return { grant_type: API_KEY_GRANT, api_key: apiKey };
}

/** An app's own token, proved with a `private_key_jwt` assertion. */
export function clientCredentialsGrant(assertion: string): Record<string, string> {
  return {
    grant_type: "client_credentials",
    client_assertion_type: ASSERTION_TYPE,
    client_assertion: assertion,
  };
}

/** An app's token exchanged (RFC 8693) for one of its space's. */
export function spaceExchangeGrant(subjectToken: string, space: string): Record<string, string> {
  return {
    grant_type: TOKEN_EXCHANGE,
    subject_token: subjectToken,
    subject_token_type: ACCESS_TOKEN_TYPE,
    space,
  };
}
