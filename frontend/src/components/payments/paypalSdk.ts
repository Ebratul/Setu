export type PaypalButtonsConfig = {
  style?: Record<string, string | number | boolean>;
  createOrder: () => Promise<string>;
  onApprove: (data: { orderID: string }) => Promise<void>;
  onCancel: () => void;
  onError: (err: unknown) => void;
};

export type PaypalNamespace = {
  Buttons: (config: PaypalButtonsConfig) => {
    render: (el: HTMLElement) => Promise<void>;
    close?: () => Promise<void> | void;
  };
};

declare global {
  interface Window {
    paypal?: PaypalNamespace;
  }
}

const SCRIPT_ID = "paypal-js-sdk";
let pending: Promise<PaypalNamespace> | null = null;

export function sdkUrl(clientId: string): string {
  return `https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(clientId)}&currency=USD&intent=capture&components=buttons`;
}

/** Injects the PayPal JS SDK once; later calls share the same promise. */
export function loadPaypalSdk(clientId: string): Promise<PaypalNamespace> {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  if (window.paypal) return Promise.resolve(window.paypal);
  if (pending) return pending;
  pending = new Promise<PaypalNamespace>((resolve, reject) => {
    const fail = () => {
      pending = null;
      document.getElementById(SCRIPT_ID)?.remove();
      reject(new Error("paypal sdk failed to load"));
    };
    let el = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
    if (!el) {
      el = document.createElement("script");
      el.id = SCRIPT_ID;
      el.src = sdkUrl(clientId);
      el.async = true;
      document.head.appendChild(el);
    }
    el.addEventListener("load", () =>
      window.paypal ? resolve(window.paypal) : fail(),
    );
    el.addEventListener("error", fail);
  });
  return pending;
}

/** Test helper. */
export function resetPaypalSdkForTests() {
  pending = null;
  document.getElementById(SCRIPT_ID)?.remove();
}
