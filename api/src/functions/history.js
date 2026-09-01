const { app } = require('@azure/functions');
const { getHistoryTable } = require('../tableClient');

const PARTITION = 'history';

app.http('historyGetAll', {
    methods: ['GET'],
    route: 'history',
    authLevel: 'anonymous',
    handler: async (request, context) => {
        try {
            const client = await getHistoryTable();
            const result = {};
            const entities = client.listEntities({ queryOptions: { filter: `PartitionKey eq '${PARTITION}'` } });
            for await (const entity of entities) {
                result[entity.rowKey] = JSON.parse(entity.data);
            }
            return { jsonBody: result };
        } catch (e) {
            context.error(e);
            return { status: 500, jsonBody: { error: e.message } };
        }
    }
});

app.http('historyPut', {
    methods: ['PUT'],
    route: 'history/{monthLabel}',
    authLevel: 'anonymous',
    handler: async (request, context) => {
        const monthLabel = request.params.monthLabel;
        try {
            const body = await request.json();
            const client = await getHistoryTable();
            await client.upsertEntity({
                partitionKey: PARTITION,
                rowKey: monthLabel,
                data: JSON.stringify(body),
                updatedAt: new Date().toISOString(),
            }, 'Replace');
            return { jsonBody: { ok: true } };
        } catch (e) {
            context.error(e);
            return { status: 500, jsonBody: { error: e.message } };
        }
    }
});

app.http('historyDelete', {
    methods: ['DELETE'],
    route: 'history/{monthLabel}',
    authLevel: 'anonymous',
    handler: async (request, context) => {
        const monthLabel = request.params.monthLabel;
        try {
            const client = await getHistoryTable();
            try {
                await client.deleteEntity(PARTITION, monthLabel);
            } catch (e) {
                if (e.statusCode !== 404) throw e;
            }
            return { jsonBody: { ok: true } };
        } catch (e) {
            context.error(e);
            return { status: 500, jsonBody: { error: e.message } };
        }
    }
});

// Bulk upsert — used by the multi-file "Bulk Upload" flow so we don't make
// one round-trip per month.
app.http('historyBulkPut', {
    methods: ['POST'],
    route: 'history/bulk',
    authLevel: 'anonymous',
    handler: async (request, context) => {
        try {
            const body = await request.json(); // { monthLabel: snapshotObj, ... }
            const client = await getHistoryTable();
            const entries = Object.entries(body || {});
            const actions = entries.map(([monthLabel, data]) => ([
                'upsert',
                { partitionKey: PARTITION, rowKey: monthLabel, data: JSON.stringify(data) },
                { mode: 'Replace' },
            ]));
            // Table transactions are capped at 100 entities per batch.
            for (let i = 0; i < actions.length; i += 100) {
                const chunk = actions.slice(i, i + 100);
                if (chunk.length) await client.submitTransaction(chunk);
            }
            return { jsonBody: { ok: true, count: entries.length } };
        } catch (e) {
            context.error(e);
            return { status: 500, jsonBody: { error: e.message } };
        }
    }
});

module.exports = {};
