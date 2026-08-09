(function (root, factory) {
    const api = factory();
    if (typeof module === "object" && module.exports) module.exports = api;
    root.EagleBridgeAuthLogic = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
    "use strict";

    function token(value) {
        return typeof value === "string" ? value : "";
    }

    function unauthorizedAction(requestToken, latestToken) {
        const requested = token(requestToken);
        const latest = token(latestToken);
        if (latest && latest !== requested) return "retry-latest";
        if (requested && latest === requested) return "clear-rejected";
        return "recover";
    }

    function createStateUpdateQueue(readState, writeState) {
        if (typeof readState !== "function" || typeof writeState !== "function") {
            throw new TypeError("State update queue requires read and write functions");
        }
        let tail = Promise.resolve();
        return function updateState(changes) {
            const operation = tail.then(async () => {
                const current = await readState();
                const patch = typeof changes === "function" ? await changes(current) : changes;
                const next = { ...current, ...(patch && typeof patch === "object" ? patch : {}) };
                await writeState(next);
                return next;
            });
            tail = operation.then(() => undefined, () => undefined);
            return operation;
        };
    }

    async function fetchWithTimeout(fetchImpl, input, options = {}, timeoutMs = 8000) {
        if (typeof fetchImpl !== "function") throw new TypeError("fetchWithTimeout requires fetch");
        const controller = new AbortController();
        const upstreamSignal = options?.signal;
        const abortFromUpstream = () => controller.abort();
        if (upstreamSignal?.aborted) controller.abort();
        else upstreamSignal?.addEventListener?.("abort", abortFromUpstream, { once: true });
        const timer = setTimeout(() => controller.abort(), Math.max(1, Number(timeoutMs) || 8000));
        try {
            return await fetchImpl(input, { ...options, signal: controller.signal });
        } finally {
            clearTimeout(timer);
            upstreamSignal?.removeEventListener?.("abort", abortFromUpstream);
        }
    }

    async function fetchJsonWithTimeout(fetchImpl, input, options = {}, timeoutMs = 8000) {
        if (typeof fetchImpl !== "function") throw new TypeError("fetchJsonWithTimeout requires fetch");
        const controller = new AbortController();
        const upstreamSignal = options?.signal;
        const abortFromUpstream = () => controller.abort();
        if (upstreamSignal?.aborted) controller.abort();
        else upstreamSignal?.addEventListener?.("abort", abortFromUpstream, { once: true });
        const timer = setTimeout(() => controller.abort(), Math.max(1, Number(timeoutMs) || 8000));
        try {
            const response = await fetchImpl(input, { ...options, signal: controller.signal });
            let result = null;
            let jsonError = null;
            try {
                result = await response.json();
            } catch (error) {
                if (controller.signal.aborted) throw error;
                jsonError = error;
            }
            return { response, result, jsonError };
        } finally {
            clearTimeout(timer);
            upstreamSignal?.removeEventListener?.("abort", abortFromUpstream);
        }
    }

    return { unauthorizedAction, createStateUpdateQueue, fetchWithTimeout, fetchJsonWithTimeout };
});
