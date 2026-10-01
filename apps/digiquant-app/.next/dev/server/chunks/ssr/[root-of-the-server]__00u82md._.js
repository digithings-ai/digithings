module.exports = [
"[externals]/next/dist/compiled/next-server/app-page-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-page-turbo.runtime.dev.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/action-async-storage.external.js [external] (next/dist/server/app-render/action-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/action-async-storage.external.js", () => require("next/dist/server/app-render/action-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-unit-async-storage.external.js [external] (next/dist/server/app-render/work-unit-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-unit-async-storage.external.js", () => require("next/dist/server/app-render/work-unit-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-async-storage.external.js [external] (next/dist/server/app-render/work-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-async-storage.external.js", () => require("next/dist/server/app-render/work-async-storage.external.js"));

module.exports = mod;
}),
"[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/lib/nav.ts [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

/**
 * Navigation tree — one source for the drop-down menu, the pinned sidebar,
 * the command line and routing. A page IS its slash-path.
 * Structure follows the canvas mock's spine; `status` mirrors its [wip]/[soon] tags.
 */ __turbopack_context__.s([
    "HOME",
    ()=>HOME,
    "NAV",
    ()=>NAV,
    "findPage",
    ()=>findPage,
    "flatPages",
    ()=>flatPages,
    "searchPages",
    ()=>searchPages,
    "sectionOf",
    ()=>sectionOf
]);
const NAV = [
    {
        title: null,
        items: [
            {
                path: '/brief',
                label: 'Brief'
            },
            {
                path: '/portfolio',
                label: 'Portfolio',
                children: [
                    {
                        path: '/portfolio/holdings',
                        label: 'Holdings'
                    },
                    {
                        path: '/portfolio/attribution',
                        label: 'Attribution'
                    },
                    {
                        path: '/portfolio/ledger',
                        label: 'Ledger'
                    },
                    {
                        path: '/portfolio/tearsheet',
                        label: 'Tearsheet'
                    },
                    {
                        path: '/portfolio/theses',
                        label: 'Theses'
                    }
                ]
            },
            {
                path: '/pipeline',
                label: 'Pipeline'
            },
            {
                path: '/strategies',
                label: 'Strategies',
                status: 'wip',
                children: [
                    {
                        path: '/strategies/detail',
                        label: 'Detail'
                    },
                    {
                        path: '/strategies/deploy',
                        label: 'Deploy'
                    }
                ]
            }
        ]
    },
    {
        title: 'tools',
        items: [
            {
                path: '/tools/terminal',
                label: 'Terminal',
                status: 'soon'
            },
            {
                path: '/tools/luxalgo',
                label: 'LuxAlgo',
                status: 'soon'
            },
            {
                path: '/tools/charts',
                label: 'Charts',
                status: 'wip'
            },
            {
                path: '/tools/chat',
                label: 'digichat',
                status: 'wip'
            },
            {
                path: '/fx',
                label: 'FX Hub',
                status: 'soon',
                children: [
                    {
                        path: '/fx/ideas',
                        label: 'Ideas'
                    },
                    {
                        path: '/fx/watch',
                        label: 'Watch'
                    },
                    {
                        path: '/fx/rates',
                        label: 'Rates'
                    },
                    {
                        path: '/fx/settings',
                        label: 'Settings'
                    }
                ]
            }
        ]
    },
    {
        title: null,
        items: [
            {
                path: '/settings',
                label: 'Settings',
                children: [
                    {
                        path: '/settings/paper',
                        label: 'Paper'
                    }
                ]
            }
        ]
    }
];
const HOME = '/brief';
function flatPages() {
    const out = [];
    const walk = (n)=>{
        out.push(n);
        n.children?.forEach(walk);
    };
    NAV.forEach((g)=>g.items.forEach(walk));
    return out;
}
function findPage(path) {
    return flatPages().find((p)=>p.path === path);
}
function searchPages(q) {
    const needle = q.trim().toLowerCase().replace(/^\//, '');
    const all = flatPages();
    if (!needle) return all;
    return all.filter((p)=>p.path.toLowerCase().includes(needle) || p.label.toLowerCase().includes(needle));
}
function sectionOf(path) {
    return '/' + (path.split('/').filter(Boolean)[0] ?? '');
}
}),
"[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/CommandLine.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "CommandLine",
    ()=>CommandLine
]);
var __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/.claude/worktrees/dashboard-shell-rebuild/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$navigation$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/.claude/worktrees/dashboard-shell-rebuild/node_modules/next/navigation.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/.claude/worktrees/dashboard-shell-rebuild/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dq$2d$dashboard$2d$atoms$2f$apps$2f$digiquant$2d$app$2f$lib$2f$nav$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/lib/nav.ts [app-ssr] (ecmascript)");
'use client';
;
;
;
;
const CommandLine = /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["forwardRef"])(function CommandLine({ pathname }, ref) {
    const router = (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$navigation$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRouter"])();
    const input = (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])(null);
    const [q, setQ] = (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null); // null = showing the current path
    const [sel, setSel] = (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(0);
    (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useImperativeHandle"])(ref, ()=>({
            focus: ()=>input.current?.focus()
        }));
    const editing = q !== null;
    const hits = editing ? (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dq$2d$dashboard$2d$atoms$2f$apps$2f$digiquant$2d$app$2f$lib$2f$nav$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["searchPages"])(q).slice(0, 8) : [];
    (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useEffect"])(()=>setSel(0), [
        q
    ]);
    const go = (path)=>{
        setQ(null);
        input.current?.blur();
        router.push(path);
    };
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "cmd",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                ref: input,
                className: "cmd-in",
                spellCheck: false,
                "aria-label": "Go to page",
                "aria-expanded": editing,
                "aria-controls": "cmd-list",
                role: "combobox",
                value: editing ? q : pathname,
                placeholder: "/ go to…",
                onFocus: (e)=>{
                    setQ('');
                    e.currentTarget.select();
                },
                onBlur: ()=>setTimeout(()=>setQ(null), 120),
                onChange: (e)=>setQ(e.target.value),
                onKeyDown: (e)=>{
                    if (e.key === 'ArrowDown') {
                        e.preventDefault();
                        setSel((s)=>Math.min(s + 1, hits.length - 1));
                    } else if (e.key === 'ArrowUp') {
                        e.preventDefault();
                        setSel((s)=>Math.max(s - 1, 0));
                    } else if (e.key === 'Enter' && hits[sel]) go(hits[sel].path);
                    else if (e.key === 'Escape') {
                        setQ(null);
                        e.currentTarget.blur();
                    }
                }
            }, void 0, false, {
                fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/CommandLine.tsx",
                lineNumber: 34,
                columnNumber: 7
            }, this),
            editing && hits.length > 0 ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("ul", {
                id: "cmd-list",
                role: "listbox",
                className: "cmd-list",
                children: hits.map((h, i)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("li", {
                        role: "option",
                        "aria-selected": i === sel,
                        className: i === sel ? 'on' : undefined,
                        onMouseDown: (e)=>{
                            e.preventDefault();
                            go(h.path);
                        },
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: h.path
                            }, void 0, false, {
                                fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/CommandLine.tsx",
                                lineNumber: 58,
                                columnNumber: 15
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "mute",
                                children: h.label
                            }, void 0, false, {
                                fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/CommandLine.tsx",
                                lineNumber: 59,
                                columnNumber: 15
                            }, this)
                        ]
                    }, h.path, true, {
                        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/CommandLine.tsx",
                        lineNumber: 57,
                        columnNumber: 13
                    }, this))
            }, void 0, false, {
                fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/CommandLine.tsx",
                lineNumber: 55,
                columnNumber: 9
            }, this) : null
        ]
    }, void 0, true, {
        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/CommandLine.tsx",
        lineNumber: 33,
        columnNumber: 5
    }, this);
});
}),
"[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/NavTree.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "NavTree",
    ()=>NavTree
]);
var __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/.claude/worktrees/dashboard-shell-rebuild/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$client$2f$app$2d$dir$2f$link$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/.claude/worktrees/dashboard-shell-rebuild/node_modules/next/dist/client/app-dir/link.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/.claude/worktrees/dashboard-shell-rebuild/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dq$2d$dashboard$2d$atoms$2f$apps$2f$digiquant$2d$app$2f$lib$2f$nav$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/lib/nav.ts [app-ssr] (ecmascript)");
'use client';
;
;
;
;
function Tag({ n }) {
    return n.status ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
        className: "nav-tag",
        children: [
            "[",
            n.status,
            "]"
        ]
    }, void 0, true, {
        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/NavTree.tsx",
        lineNumber: 8,
        columnNumber: 21
    }, this) : null;
}
function NavTree({ pathname, variant, onNavigate }) {
    const [open, setOpen] = (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])({});
    const active = (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dq$2d$dashboard$2d$atoms$2f$apps$2f$digiquant$2d$app$2f$lib$2f$nav$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["sectionOf"])(pathname);
    const isOpen = (p)=>variant === 'menu' || (open[p] ?? p === active);
    let no = 0;
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("nav", {
        className: `navtree ${variant}`,
        "aria-label": "Pages",
        children: __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dq$2d$dashboard$2d$atoms$2f$apps$2f$digiquant$2d$app$2f$lib$2f$nav$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["NAV"].map((g, gi)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "nav-group",
                children: [
                    g.title ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "nav-title",
                        children: g.title
                    }, void 0, false, {
                        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/NavTree.tsx",
                        lineNumber: 26,
                        columnNumber: 22
                    }, this) : null,
                    g.items.map((n)=>{
                        no += 1;
                        const num = String(no).padStart(2, '0');
                        const here = pathname === n.path;
                        const hasKids = !!n.children?.length;
                        return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "nav-row",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$client$2f$app$2d$dir$2f$link$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["default"], {
                                            href: n.path,
                                            onClick: onNavigate,
                                            className: `nav-link${here ? ' on' : ''}`,
                                            "aria-current": here ? 'page' : undefined,
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "nav-no",
                                                    children: num
                                                }, void 0, false, {
                                                    fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/NavTree.tsx",
                                                    lineNumber: 36,
                                                    columnNumber: 21
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    children: n.label
                                                }, void 0, false, {
                                                    fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/NavTree.tsx",
                                                    lineNumber: 37,
                                                    columnNumber: 21
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(Tag, {
                                                    n: n
                                                }, void 0, false, {
                                                    fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/NavTree.tsx",
                                                    lineNumber: 38,
                                                    columnNumber: 21
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/NavTree.tsx",
                                            lineNumber: 35,
                                            columnNumber: 19
                                        }, this),
                                        hasKids && variant === 'rail' ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                            type: "button",
                                            className: "nav-twist",
                                            "aria-expanded": isOpen(n.path),
                                            "aria-label": `${isOpen(n.path) ? 'Collapse' : 'Expand'} ${n.label}`,
                                            onClick: ()=>setOpen((o)=>({
                                                        ...o,
                                                        [n.path]: !isOpen(n.path)
                                                    })),
                                            children: isOpen(n.path) ? '–' : '+'
                                        }, void 0, false, {
                                            fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/NavTree.tsx",
                                            lineNumber: 41,
                                            columnNumber: 21
                                        }, this) : null
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/NavTree.tsx",
                                    lineNumber: 34,
                                    columnNumber: 17
                                }, this),
                                hasKids && isOpen(n.path) ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "nav-kids",
                                    children: n.children.map((c)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$client$2f$app$2d$dir$2f$link$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["default"], {
                                            href: c.path,
                                            onClick: onNavigate,
                                            className: `nav-link kid${pathname === c.path ? ' on' : ''}`,
                                            "aria-current": pathname === c.path ? 'page' : undefined,
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    children: c.label
                                                }, void 0, false, {
                                                    fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/NavTree.tsx",
                                                    lineNumber: 56,
                                                    columnNumber: 25
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(Tag, {
                                                    n: c
                                                }, void 0, false, {
                                                    fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/NavTree.tsx",
                                                    lineNumber: 57,
                                                    columnNumber: 25
                                                }, this)
                                            ]
                                        }, c.path, true, {
                                            fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/NavTree.tsx",
                                            lineNumber: 55,
                                            columnNumber: 23
                                        }, this))
                                }, void 0, false, {
                                    fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/NavTree.tsx",
                                    lineNumber: 53,
                                    columnNumber: 19
                                }, this) : null
                            ]
                        }, n.path, true, {
                            fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/NavTree.tsx",
                            lineNumber: 33,
                            columnNumber: 15
                        }, this);
                    })
                ]
            }, gi, true, {
                fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/NavTree.tsx",
                lineNumber: 25,
                columnNumber: 9
            }, this))
    }, void 0, false, {
        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/NavTree.tsx",
        lineNumber: 23,
        columnNumber: 5
    }, this);
}
}),
"[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Shell.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "Shell",
    ()=>Shell
]);
var __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/.claude/worktrees/dashboard-shell-rebuild/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$navigation$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/.claude/worktrees/dashboard-shell-rebuild/node_modules/next/navigation.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/.claude/worktrees/dashboard-shell-rebuild/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dq$2d$dashboard$2d$atoms$2f$apps$2f$digiquant$2d$app$2f$components$2f$CommandLine$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/CommandLine.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dq$2d$dashboard$2d$atoms$2f$apps$2f$digiquant$2d$app$2f$components$2f$NavTree$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/NavTree.tsx [app-ssr] (ecmascript)");
'use client';
;
;
;
;
;
const PIN_KEY = 'dq-nav-pinned';
function Shell({ children }) {
    const pathname = (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$navigation$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["usePathname"])() || '/';
    const [menu, setMenu] = (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(false);
    const [pinned, setPinned] = (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(false);
    const cmd = (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])(null);
    (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useEffect"])(()=>{
        try {
            setPinned(localStorage.getItem(PIN_KEY) === '1');
        } catch  {}
    }, []);
    const togglePin = ()=>{
        setPinned((p)=>{
            try {
                localStorage.setItem(PIN_KEY, p ? '0' : '1');
            } catch  {}
            return !p;
        });
        setMenu(false);
    };
    (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useEffect"])(()=>{
        const onKey = (e)=>{
            const t = e.target;
            const typing = t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement;
            if (e.key === 'k' && (e.metaKey || e.ctrlKey) || e.key === '/' && !typing) {
                e.preventDefault();
                cmd.current?.focus();
            } else if (e.key === 'Escape') setMenu(false);
        };
        window.addEventListener('keydown', onKey);
        return ()=>window.removeEventListener('keydown', onKey);
    }, []);
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: `shell${pinned ? ' has-rail' : ''}`,
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                className: "top",
                children: [
                    pinned ? null : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        type: "button",
                        className: "top-btn",
                        "aria-expanded": menu,
                        "aria-controls": "nav-menu",
                        onClick: ()=>setMenu((m)=>!m),
                        children: [
                            "menu ",
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                "aria-hidden": true,
                                children: menu ? '▴' : '▾'
                            }, void 0, false, {
                                fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Shell.tsx",
                                lineNumber: 50,
                                columnNumber: 18
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Shell.tsx",
                        lineNumber: 49,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        className: "brand",
                        children: "DIGIQUANT"
                    }, void 0, false, {
                        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Shell.tsx",
                        lineNumber: 53,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dq$2d$dashboard$2d$atoms$2f$apps$2f$digiquant$2d$app$2f$components$2f$CommandLine$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["CommandLine"], {
                        ref: cmd,
                        pathname: pathname
                    }, void 0, false, {
                        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Shell.tsx",
                        lineNumber: 54,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        className: "top-spacer"
                    }, void 0, false, {
                        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Shell.tsx",
                        lineNumber: 55,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        type: "button",
                        className: `top-btn${pinned ? ' on' : ''}`,
                        "aria-pressed": pinned,
                        onClick: togglePin,
                        title: "Keep the navigation on the page",
                        children: pinned ? 'unpin nav' : 'pin nav'
                    }, void 0, false, {
                        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Shell.tsx",
                        lineNumber: 56,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Shell.tsx",
                lineNumber: 47,
                columnNumber: 7
            }, this),
            menu && !pinned ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Fragment"], {
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "scrim",
                        onClick: ()=>setMenu(false)
                    }, void 0, false, {
                        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Shell.tsx",
                        lineNumber: 63,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        id: "nav-menu",
                        className: "drop",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dq$2d$dashboard$2d$atoms$2f$apps$2f$digiquant$2d$app$2f$components$2f$NavTree$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["NavTree"], {
                                pathname: pathname,
                                variant: "menu",
                                onNavigate: ()=>setMenu(false)
                            }, void 0, false, {
                                fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Shell.tsx",
                                lineNumber: 65,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "drop-foot mute",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "/ or ⌘K — go to any page by path"
                                    }, void 0, false, {
                                        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Shell.tsx",
                                        lineNumber: 67,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                        type: "button",
                                        className: "top-btn",
                                        onClick: togglePin,
                                        children: "pin as sidebar"
                                    }, void 0, false, {
                                        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Shell.tsx",
                                        lineNumber: 68,
                                        columnNumber: 15
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Shell.tsx",
                                lineNumber: 66,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Shell.tsx",
                        lineNumber: 64,
                        columnNumber: 11
                    }, this)
                ]
            }, void 0, true) : null,
            pinned ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("aside", {
                className: "rail",
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dq$2d$dashboard$2d$atoms$2f$apps$2f$digiquant$2d$app$2f$components$2f$NavTree$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["NavTree"], {
                    pathname: pathname,
                    variant: "rail"
                }, void 0, false, {
                    fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Shell.tsx",
                    lineNumber: 76,
                    columnNumber: 11
                }, this)
            }, void 0, false, {
                fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Shell.tsx",
                lineNumber: 75,
                columnNumber: 9
            }, this) : null,
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f2e$claude$2f$worktrees$2f$dashboard$2d$shell$2d$rebuild$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("main", {
                className: "main",
                children: children
            }, void 0, false, {
                fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Shell.tsx",
                lineNumber: 80,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/.claude/worktrees/dq-dashboard-atoms/apps/digiquant-app/components/Shell.tsx",
        lineNumber: 46,
        columnNumber: 5
    }, this);
}
}),
"[externals]/next/dist/server/app-render/after-task-async-storage.external.js [external] (next/dist/server/app-render/after-task-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/after-task-async-storage.external.js", () => require("next/dist/server/app-render/after-task-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/dynamic-access-async-storage.external.js [external] (next/dist/server/app-render/dynamic-access-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/dynamic-access-async-storage.external.js", () => require("next/dist/server/app-render/dynamic-access-async-storage.external.js"));

module.exports = mod;
}),
];

//# sourceMappingURL=%5Broot-of-the-server%5D__00u82md._.js.map