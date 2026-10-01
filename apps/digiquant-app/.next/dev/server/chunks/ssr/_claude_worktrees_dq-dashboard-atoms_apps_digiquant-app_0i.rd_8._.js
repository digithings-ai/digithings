module.exports = [
"[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/lib/dq-api.ts [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

/**
 * DigiQuant API client — the dashboard-api worker (apps/dashboard-api,
 * CONTRACT.md §6). Every data block binds to one route here.
 */ __turbopack_context__.s([
    "dqGet",
    ()=>dqGet,
    "pct",
    ()=>pct,
    "px",
    ()=>px,
    "signed",
    ()=>signed
]);
const base = ()=>(("TURBOPACK compile-time value", "http://localhost:8787") ?? '').replace(/\/+$/, '');
async function dqGet(route) {
    if (!base()) throw new Error('NEXT_PUBLIC_DQ_API_URL is not set');
    const res = await fetch(`${base()}${route}`);
    if (!res.ok) throw new Error(`${route} failed (${res.status})`);
    return await res.json();
}
const pct = (v)=>v === null || !Number.isFinite(v) ? '—' : `${v.toFixed(2)}%`;
const px = (v)=>v === null || !Number.isFinite(v) ? '—' : v.toFixed(2);
const signed = (v)=>v === null || !Number.isFinite(v) ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;
}),
"[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/DataTable.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "DataTable",
    ()=>DataTable
]);
var __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/.claude/worktrees/dashboard-shell-rebuild/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
;
function DataTable({ rows, cols, rowKey }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("table", {
        className: "tbl",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("thead", {
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tr", {
                    children: cols.map((c)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("th", {
                            className: c.num ? 'num' : undefined,
                            children: c.label
                        }, c.key, false, {
                            fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/DataTable.tsx",
                            lineNumber: 10,
                            columnNumber: 30
                        }, this))
                }, void 0, false, {
                    fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/DataTable.tsx",
                    lineNumber: 10,
                    columnNumber: 9
                }, this)
            }, void 0, false, {
                fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/DataTable.tsx",
                lineNumber: 9,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tbody", {
                children: rows.map((r)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("tr", {
                        children: cols.map((c)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("td", {
                                className: [
                                    c.num ? 'num' : '',
                                    c.tone?.(r) ?? ''
                                ].join(' ').trim() || undefined,
                                children: c.cell(r)
                            }, c.key, false, {
                                fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/DataTable.tsx",
                                lineNumber: 15,
                                columnNumber: 30
                            }, this))
                    }, rowKey(r), false, {
                        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/DataTable.tsx",
                        lineNumber: 14,
                        columnNumber: 11
                    }, this))
            }, void 0, false, {
                fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/DataTable.tsx",
                lineNumber: 12,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/DataTable.tsx",
        lineNumber: 8,
        columnNumber: 5
    }, this);
}
}),
"[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Window.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "Window",
    ()=>Window
]);
var __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/.claude/worktrees/dashboard-shell-rebuild/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
;
function Window({ no, label, right, children }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
        className: "win",
        "aria-label": label,
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                className: "win-bar",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        className: "ey",
                        children: [
                            no,
                            " / ",
                            label
                        ]
                    }, void 0, true, {
                        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Window.tsx",
                        lineNumber: 8,
                        columnNumber: 9
                    }, this),
                    right ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        children: right
                    }, void 0, false, {
                        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Window.tsx",
                        lineNumber: 9,
                        columnNumber: 18
                    }, this) : null
                ]
            }, void 0, true, {
                fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Window.tsx",
                lineNumber: 7,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "win-body",
                children: children
            }, void 0, false, {
                fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Window.tsx",
                lineNumber: 11,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Window.tsx",
        lineNumber: 6,
        columnNumber: 5
    }, this);
}
}),
"[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/BookTable.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "BookTable",
    ()=>BookTable
]);
var __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/.claude/worktrees/dashboard-shell-rebuild/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/.claude/worktrees/dashboard-shell-rebuild/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dq$2d$dashboard$2d$atoms$2f$apps$2f$digiquant$2d$app$2f$lib$2f$dq$2d$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/lib/dq-api.ts [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dq$2d$dashboard$2d$atoms$2f$apps$2f$digiquant$2d$app$2f$components$2f$DataTable$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/DataTable.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dq$2d$dashboard$2d$atoms$2f$apps$2f$digiquant$2d$app$2f$components$2f$Window$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Window.tsx [app-ssr] (ecmascript)");
'use client';
;
;
;
;
;
const cols = [
    {
        key: 't',
        label: 'Ticker',
        cell: (r)=>r.ticker
    },
    {
        key: 'w',
        label: 'Weight',
        num: true,
        cell: (r)=>(0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dq$2d$dashboard$2d$atoms$2f$apps$2f$digiquant$2d$app$2f$lib$2f$dq$2d$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["pct"])(r.scaled_weight_pct)
    },
    {
        key: 'e',
        label: 'Entry',
        num: true,
        cell: (r)=>(0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dq$2d$dashboard$2d$atoms$2f$apps$2f$digiquant$2d$app$2f$lib$2f$dq$2d$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["px"])(r.entry_price)
    },
    {
        key: 'm',
        label: 'Mark',
        num: true,
        cell: (r)=>(0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dq$2d$dashboard$2d$atoms$2f$apps$2f$digiquant$2d$app$2f$lib$2f$dq$2d$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["px"])(r.current_price)
    },
    {
        key: 'u',
        label: 'Unrealised',
        num: true,
        cell: (r)=>(0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dq$2d$dashboard$2d$atoms$2f$apps$2f$digiquant$2d$app$2f$lib$2f$dq$2d$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["signed"])(r.unrealized_pct),
        tone: (r)=>r.unrealized_pct === null ? undefined : r.unrealized_pct >= 0 ? 'pos' : 'neg'
    }
];
function BookTable() {
    const [book, setBook] = (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    const [err, setErr] = (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useEffect"])(()=>{
        (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dq$2d$dashboard$2d$atoms$2f$apps$2f$digiquant$2d$app$2f$lib$2f$dq$2d$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["dqGet"])('/allocations').then((e)=>setBook(e.data)).catch((e)=>setErr(e instanceof Error ? e.message : 'failed'));
    }, []);
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dq$2d$dashboard$2d$atoms$2f$apps$2f$digiquant$2d$app$2f$components$2f$Window$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Window"], {
        no: "03",
        label: "Book · allocation",
        right: book?.book_as_of ? `as of ${book.book_as_of}` : undefined,
        children: err ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
            className: "note",
            role: "alert",
            children: err
        }, void 0, false, {
            fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/BookTable.tsx",
            lineNumber: 30,
            columnNumber: 14
        }, this) : !book ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
            className: "note mute",
            children: "loading…"
        }, void 0, false, {
            fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/BookTable.tsx",
            lineNumber: 31,
            columnNumber: 19
        }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dq$2d$dashboard$2d$atoms$2f$apps$2f$digiquant$2d$app$2f$components$2f$DataTable$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["DataTable"], {
            rows: book.rows,
            cols: cols,
            rowKey: (r)=>r.ticker
        }, void 0, false, {
            fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/BookTable.tsx",
            lineNumber: 32,
            columnNumber: 11
        }, this)
    }, void 0, false, {
        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/BookTable.tsx",
        lineNumber: 29,
        columnNumber: 5
    }, this);
}
}),
];

//# sourceMappingURL=_claude_worktrees_dq-dashboard-atoms_apps_digiquant-app_0i.rd_8._.js.map