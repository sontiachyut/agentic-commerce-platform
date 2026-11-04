export type Actor = { user_id: string; role: string };
export type Product = {
  id: string;
  name: string;
  category: string;
  description: string;
  price_minor: number;
  available: number;
};
export type Quote = {
  id: string;
  product_id: string;
  product_name: string;
  amount_minor: number;
  digest: string;
  expires_at: number;
  kiosk_id: string;
};
export type Execution = {
  id: string;
  order_id: string;
  state: string;
  stage: string;
  payment_state: string;
  fulfillment_state: string;
  compensation_state: string;
  failure_code: string | null;
  outcome: { success: boolean; message: string };
  version: number;
};
export type Event = {
  id: string;
  type: string;
  data: Record<string, unknown>;
  created_at: number;
};
export type Session = {
  id: string;
  original_request: string;
  state: string;
  message: string;
  quote: Quote | null;
  execution: Execution | null;
  events: Event[];
  model_provider: string;
};
export type History = {
  id: string;
  request: string;
  state: string;
  created_at: number;
};
export type Grant = {
  id: string;
  total_minor: number;
  spent_minor: number;
  held_minor: number;
  per_purchase_minor: number;
  expires_at: number;
  revoked: boolean;
  version: number;
  product_ids: string[];
};
export type Overview = {
  executions: Execution[];
  jobs: {
    id: string;
    kind: string;
    state: string;
    attempts: number;
    resource_id: string;
    last_error: string | null;
  }[];
  events: Event[];
};
