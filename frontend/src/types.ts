export interface MediaItem {
  id: number;
  title: string;
  category: string;
  platform: string | null;
  genre: string;
  genres: string | null;
  year_released: number | null;
  release_date: string | null;
  rating: string | null;
  players: number | null;
  cooperative: string | null;
  artist: string | null;
  publisher: string | null;
  format: string | null;
  region: string | null;
  cover_image: string | null;
  spine_image: string | null;
  disc_image: string | null;
  tags: string | null;
  notes: string | null;
  star_rating: number | null;
  gameplay_rating: number | null;
  plot_rating: number | null;
}

export interface EditableSystem {
  id: string;
  name: string;
  shortName: string;
  logo: string;
  logoImage: string | null;
  caseType?: 'disc' | 'cartridge' | 'hybrid';
  appearancePreset?: string | null;
  isCartridgeInferred?: boolean;
  displayOrder?: number;
}
