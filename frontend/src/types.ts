export interface MediaItem {
  id: number;
  title: string;
  category: string;
  platform: string | null;
  genre: string;
  year_released: number | null;
  players: number | null;
  artist: string | null;
  publisher: string | null;
  format: string | null;
  region: string | null;
  cover_image: string | null;
  tags: string | null;
  notes: string | null;
}
