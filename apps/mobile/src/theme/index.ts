/**
 * Design tokens. One file so screens never invent a colour or a spacing value inline.
 */

export const colors = {
  background: "#0f1115",
  surface: "#181b22",
  surfaceMuted: "#20242d",
  border: "#2a2f3a",
  text: "#f2f4f8",
  textMuted: "#9aa3b2",
  accent: "#4f8cff",
  accentPressed: "#3a6fd8",
  success: "#3fb56b",
  warning: "#e0a33e",
  danger: "#e05a5a",
  ratingStrong: "#3fb56b",
  ratingDeveloping: "#e0a33e",
  ratingNeedsWork: "#e05a5a",
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

export const radius = {
  sm: 6,
  md: 10,
  lg: 16,
  pill: 999,
} as const;

export const typography = {
  title: { fontSize: 24, fontWeight: "700" },
  heading: { fontSize: 18, fontWeight: "600" },
  body: { fontSize: 15, fontWeight: "400" },
  label: { fontSize: 13, fontWeight: "600" },
  caption: { fontSize: 12, fontWeight: "400" },
} as const;

export const ratingLabels: Record<string, string> = {
  strong: "稳",
  developing: "在进步",
  needs_work: "要练",
};

export const ratingColors: Record<string, string> = {
  strong: colors.ratingStrong,
  developing: colors.ratingDeveloping,
  needs_work: colors.ratingNeedsWork,
};

export const dimensionLabels: Record<string, string> = {
  clarity: "清晰度",
  fluency: "流畅度",
  naturalness: "自然度",
  professional_tone: "职场语气",
  response_relevance: "是否答到点上",
};

export const categoryLabels: Record<string, string> = {
  interview: "面试",
  workplace: "职场",
  travel: "出差",
  daily_life: "生活",
};

export const reviewItemTypeLabels: Record<string, string> = {
  expression: "表达",
  grammar: "语法",
  clarity: "清晰度",
  pronunciation: "发音",
  communication: "沟通",
};

export const reviewStatusLabels: Record<string, string> = {
  new: "待复习",
  reviewing: "复习中",
  mastered: "已掌握",
  archived: "已归档",
};

export const errorCodeLabels: Record<string, string> = {
  ai_provider_timeout: "模型超时",
  ai_provider_error: "模型调用失败",
  invalid_ai_output: "模型输出不合格，已拦下",
};
