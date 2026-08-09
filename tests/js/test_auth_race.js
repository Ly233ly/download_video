const path = require("path");

const root = path.resolve(__dirname, "..", "..");
const auth = require(path.join(root, "chrome-extension", "js", "eagle-bridge-auth-logic.js"));

if (auth.unauthorizedAction("", "new-token") !== "retry-latest") {
    throw new Error("A pre-pair 401 must not erase a token created while the request was in flight");
}

if (auth.unauthorizedAction("old-token", "new-token") !== "retry-latest") {
    throw new Error("A stale rejected token must retry with the newer stored token");
}

if (auth.unauthorizedAction("rejected-token", "rejected-token") !== "clear-rejected") {
    throw new Error("Only the exact token rejected by the helper may be cleared");
}

if (auth.unauthorizedAction("", "") !== "recover") {
    throw new Error("A request with no available token should use normal pairing recovery");
}

(async () => {
    let aborted = false;
    const neverReturns = (_url, options) => new Promise((_resolve, reject) => {
        options.signal.addEventListener("abort", () => {
            aborted = true;
            reject(new Error("aborted"));
        }, { once: true });
    });
    const timeoutStarted = Date.now();
    await auth.fetchWithTimeout(neverReturns, "http://127.0.0.1/health", {}, 25)
        .then(() => { throw new Error("a hung desktop request must time out"); })
        .catch(error => {
            if (!/aborted/i.test(String(error?.message || error))) throw error;
        });
    if (!aborted || Date.now() - timeoutStarted > 500) {
        throw new Error("desktop fetch timeout did not abort deterministically");
    }

    const stalledBody = async (_url, options) => ({
        ok: true,
        status: 200,
        json() {
            return new Promise((_resolve, reject) => {
                options.signal.addEventListener("abort", () => reject(new Error("body aborted")), { once: true });
            });
        }
    });
    await auth.fetchJsonWithTimeout(stalledBody, "http://127.0.0.1/api/plans", {}, 25)
        .then(() => { throw new Error("a stalled response body must time out"); })
        .catch(error => {
            if (!/body aborted/i.test(String(error?.message || error))) throw error;
        });

    let stored = { token: "", pendingEvents: [], lastPlanId: "plan", lastPlanStatus: "queued" };
    const update = auth.createStateUpdateQueue(
        async () => {
            const snapshot = { ...stored, pendingEvents: [...stored.pendingEvents] };
            await Promise.resolve();
            return snapshot;
        },
        async next => {
            await Promise.resolve();
            stored = next;
        }
    );

    await Promise.all([
        update({ token: "new-token" }),
        update({ lastPlanStatus: "queued" })
    ]);
    if (stored.token !== "new-token") {
        throw new Error("Concurrent non-auth state writes must not overwrite a newly paired token");
    }

    await update(current => current.token === "old-token" ? { token: "" } : {});
    if (stored.token !== "new-token") {
        throw new Error("Conditional token clearing must re-check the token inside the serialized write");
    }

    console.log("Pairing token race recovery OK");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
