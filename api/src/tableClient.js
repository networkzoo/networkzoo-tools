const { TableClient } = require("@azure/data-tables");

// Falls back to the Functions runtime's own storage account (AzureWebJobsStorage)
// if a dedicated TABLES_CONNECTION_STRING isn't set. Either works fine for this
// app's tiny data volume.
const CONN_STR = process.env.TABLES_CONNECTION_STRING || process.env.AzureWebJobsStorage;

const CONFIG_TABLE  = "SophosConfig";
const HISTORY_TABLE = "SophosHistory";

const tableCache = {};

function getTable(tableName) {
    if (!CONN_STR) {
        throw new Error("No storage connection string configured (TABLES_CONNECTION_STRING or AzureWebJobsStorage).");
    }
    if (!tableCache[tableName]) {
        tableCache[tableName] = TableClient.fromConnectionString(CONN_STR, tableName, {
            allowInsecureConnection: CONN_STR.includes("UseDevelopmentStorage=true"),
        });
    }
    return tableCache[tableName];
}

async function ensureTable(client) {
    try {
        await client.createTable();
    } catch (e) {
        // 409 = already exists, which is fine
        if (e.statusCode !== 409) throw e;
    }
}

async function getConfigTable() {
    const client = getTable(CONFIG_TABLE);
    await ensureTable(client);
    return client;
}

async function getHistoryTable() {
    const client = getTable(HISTORY_TABLE);
    await ensureTable(client);
    return client;
}

module.exports = { getConfigTable, getHistoryTable };
