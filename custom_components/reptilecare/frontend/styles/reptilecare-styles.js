export const sharedCardStyles = `
  :host {
    display: block;
    color: var(--primary-text-color);
    font-family: var(--paper-font-body1_-_font-family, inherit);
  }

  button {
    font: inherit;
  }

  .action-button,
  .quick-action-button {
    border: 1px solid var(--divider-color);
    border-radius: 999px;
    background: var(--card-background-color);
    color: var(--primary-text-color);
    cursor: pointer;
    padding: 0.55rem 0.9rem;
    transition: background 120ms ease, border-color 120ms ease, transform 120ms ease;
  }

  .action-button:hover,
  .quick-action-button:hover {
    border-color: var(--primary-color);
    background: color-mix(in srgb, var(--primary-color) 10%, var(--card-background-color));
  }

  .action-button:focus-visible,
  .quick-action-button:focus-visible,
  .icon-button:focus-visible,
  .dialog-button:focus-visible,
  .dialog-close:focus-visible {
    outline: 2px solid var(--primary-color);
    outline-offset: 2px;
  }

  .action-button:disabled,
  .quick-action-button:disabled,
  .icon-button:disabled,
  .dialog-button:disabled,
  .dialog-close:disabled {
    opacity: 0.55;
    cursor: default;
  }
`;

