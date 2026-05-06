import "@testing-library/jest-dom";
import { vi } from "vitest";

// jsdom does not implement scrollIntoView
window.HTMLElement.prototype.scrollIntoView = vi.fn(function () {});
