import { apiClient } from "./client";

export interface ArticleListItem {
  id: string;
  slug: string;
  title: string;
  category: string | null;
  display_order: number;
  excerpt: string;
  is_published: boolean;
  updated_at: string;
}

export interface ArticleRead {
  id: string;
  slug: string;
  title: string;
  category: string | null;
  display_order: number;
  content: string;
  is_published: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ArticleCreate {
  title: string;
  slug?: string;
  category?: string | null;
  display_order?: number;
  content?: string;
  is_published?: boolean;
}

export interface ArticleUpdate {
  title?: string;
  category?: string | null;
  display_order?: number;
  content?: string;
  is_published?: boolean;
}

export interface ImageUploadResponse {
  id: string;
  url: string;
}

export async function listArticles(params?: { category?: string; q?: string }): Promise<ArticleListItem[]> {
  const { data } = await apiClient.get<ArticleListItem[]>("/kb/articles", { params });
  return data;
}

export async function listCategories(): Promise<string[]> {
  const { data } = await apiClient.get<string[]>("/kb/categories");
  return data;
}

export async function getArticle(idOrSlug: string): Promise<ArticleRead> {
  const { data } = await apiClient.get<ArticleRead>(`/kb/articles/${idOrSlug}`);
  return data;
}

export async function createArticle(body: ArticleCreate): Promise<ArticleRead> {
  const { data } = await apiClient.post<ArticleRead>("/kb/articles", body);
  return data;
}

export async function updateArticle(idOrSlug: string, body: ArticleUpdate): Promise<ArticleRead> {
  const { data } = await apiClient.patch<ArticleRead>(`/kb/articles/${idOrSlug}`, body);
  return data;
}

export async function deleteArticle(idOrSlug: string): Promise<void> {
  await apiClient.delete(`/kb/articles/${idOrSlug}`);
}

export async function uploadArticleImage(file: File, articleId?: string): Promise<ImageUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await apiClient.post<ImageUploadResponse>("/kb/images", form, {
    headers: { "Content-Type": "multipart/form-data" },
    params: articleId ? { article_id: articleId } : undefined,
  });
  return data;
}
