export const sharedCardStyles = `
  :host {
    display: block;
    color: var(--primary-text-color);
    font-family: var(--paper-font-body1_-_font-family, inherit);
  }

  *,
  *::before,
  *::after {
    box-sizing: border-box;
  }

  button,
  input,
  textarea {
    font: inherit;
  }

  .action-button,
  .quick-action-button,
  .dialog-button {
    min-height: 2.75rem;
    border: 1px solid var(--divider-color);
    border-radius: 999px;
    background: var(--card-background-color);
    color: var(--primary-text-color);
    cursor: pointer;
    padding: 0.65rem 1rem;
    transition:
      background 160ms ease,
      border-color 160ms ease,
      color 160ms ease,
      transform 160ms ease,
      opacity 160ms ease;
  }

  .action-button:hover,
  .quick-action-button:hover,
  .dialog-button:hover {
    border-color: var(--primary-color);
    background: color-mix(in srgb, var(--primary-color) 10%, var(--card-background-color));
  }

  .action-button:active,
  .quick-action-button:active,
  .icon-button:active,
  .dialog-button:active {
    transform: translateY(1px);
  }

  .action-button:focus-visible,
  .quick-action-button:focus-visible,
  .icon-button:focus-visible,
  .dialog-button:focus-visible,
  .dialog-close:focus-visible,
  .field-input:focus-visible,
  .notes-input:focus-visible {
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

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

  .busy-indicator {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    color: var(--secondary-text-color);
    font-size: 0.88rem;
    font-weight: 600;
  }

  .busy-indicator::before {
    content: "";
    width: 0.9rem;
    height: 0.9rem;
    border: 2px solid color-mix(in srgb, var(--primary-color) 28%, transparent);
    border-top-color: var(--primary-color);
    border-radius: 999px;
    animation: reptilecare-spin 700ms linear infinite;
  }

  @keyframes reptilecare-spin {
    to {
      transform: rotate(360deg);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
      animation-duration: 0.01ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.01ms !important;
      scroll-behavior: auto !important;
    }
  }
`;
