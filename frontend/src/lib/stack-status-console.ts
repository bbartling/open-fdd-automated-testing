/** Browser console helpers for the dashboard Stack strip (API / BACnet / MQTT). */

export const STACK_STATUS_LOG_PREFIX = "[OpenFDD Stack]";

/** Successful polls (use Verbose / All levels in DevTools to see `debug` output). */
export function stackStatusConsoleDebug(message: string, data?: Record<string, unknown>): void {
  if (data !== undefined) {
    console.debug(`${STACK_STATUS_LOG_PREFIX} ${message}`, data);
  } else {
    console.debug(`${STACK_STATUS_LOG_PREFIX} ${message}`);
  }
}

export function stackStatusConsoleWarn(message: string, data?: Record<string, unknown>): void {
  if (data !== undefined) {
    console.warn(`${STACK_STATUS_LOG_PREFIX} ${message}`, data);
  } else {
    console.warn(`${STACK_STATUS_LOG_PREFIX} ${message}`);
  }
}

export function stackStatusConsoleError(message: string, data?: Record<string, unknown>): void {
  if (data !== undefined) {
    console.error(`${STACK_STATUS_LOG_PREFIX} ${message}`, data);
  } else {
    console.error(`${STACK_STATUS_LOG_PREFIX} ${message}`);
  }
}
