// Cube security. The JWT payload (signed with CUBEJS_API_SECRET) becomes `securityContext`:
//   { role: 'cmo' | 'branch_manager' | 'analyst', branch_id?: number, sub: string }
// Every query passes through queryRewrite, so the rules below hold for chat, dashboards and external MCP clients alike.

const ROLES = ['cmo', 'branch_manager', 'analyst'];
// Cubes that carry a branch_id dimension and can therefore be row-filtered for a branch manager.
const BRANCH_SCOPED = ['customers', 'accounts', 'balances', 'loans', 'transactions', 'campaigns', 'branches'];

const memberCubes = (query) => {
  const members = [
    ...(query.measures || []),
    ...(query.dimensions || []),
    ...(query.segments || []),
    ...(query.timeDimensions || []).map((t) => t.dimension),
  ];
  const walk = (filters) => {
    for (const f of filters || []) {
      if (f.member) members.push(f.member);
      if (f.and) walk(f.and);
      if (f.or) walk(f.or);
    }
  };
  walk(query.filters);
  return members;
};

module.exports = {
  queryRewrite: (query, { securityContext }) => {
    const role = securityContext && securityContext.role;
    if (!ROLES.includes(role)) {
      throw new Error('Access denied: token has no valid role');
    }
    const members = memberCubes(query);

    if (role === 'analyst' && members.some((m) => m.endsWith('_key'))) {
      throw new Error('Access denied: the analyst role cannot query customer-level dimensions');
    }

    if (role === 'branch_manager') {
      const branchId = securityContext.branch_id;
      if (branchId === undefined || branchId === null) {
        throw new Error('Access denied: branch_manager token has no branch_id');
      }
      const cubes = [...new Set(members.map((m) => m.split('.')[0]))];
      for (const cube of cubes) {
        if (!BRANCH_SCOPED.includes(cube)) {
          throw new Error(`Access denied: ${cube} is bank-wide data and not available to branch managers`);
        }
        query.filters = query.filters || [];
        query.filters.push({ member: `${cube}.branch_id`, operator: 'equals', values: [String(branchId)] });
      }
    }
    return query;
  },
};
