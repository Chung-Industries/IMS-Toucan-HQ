import json
import os.path

from geopy.distance import geodesic
from tqdm import tqdm
import torch
import argparse
from Utility.storage_config import MODELS_DIR


class CacheCreator:
    def __init__(self, cache_root="."):
        self.iso_codes = list(load_json_from_path(os.path.join(cache_root, "iso_to_fullname.json")).keys())
        self.iso_lookup = load_json_from_path(os.path.join(cache_root, "iso_lookup.json"))
        self.pairs = list()  # ignore order, collect all language pairs
        for index_1 in tqdm(range(len(self.iso_codes)), desc="Collecting language pairs"):
            for index_2 in range(index_1, len(self.iso_codes)):
                self.pairs.append((self.iso_codes[index_1], self.iso_codes[index_2]))

    def create_tree_cache(self, cache_root="."):
        iso_to_family_memberships = load_json_from_path(os.path.join(cache_root, "iso_to_memberships.json"))

        self.pair_to_tree_similarity = dict()
        self.pair_to_depth = dict()
        for pair in tqdm(self.pairs):
            self.pair_to_tree_similarity[pair] = len(set(iso_to_family_memberships[pair[0]]).intersection(set(iso_to_family_memberships[pair[1]])))
            self.pair_to_depth[pair] = len(iso_to_family_memberships[pair[0]]) + len(iso_to_family_memberships[pair[1]])
        
        lang_1_to_lang_2_to_tree_dist = dict()
        for pair in self.pair_to_tree_similarity:
            lang_1 = pair[0]
            lang_2 = pair[1]
            if self.pair_to_tree_similarity[pair] == 2:
                dist = 1.0
            else:
                dist = 1 - ((self.pair_to_tree_similarity[pair] * 2) / self.pair_to_depth[pair])
            if lang_1 not in lang_1_to_lang_2_to_tree_dist.keys():
                lang_1_to_lang_2_to_tree_dist[lang_1] = dict()
            lang_1_to_lang_2_to_tree_dist[lang_1][lang_2] = dist
        with open(os.path.join(cache_root, 'lang_1_to_lang_2_to_tree_dist.json'), 'w', encoding='utf-8') as f:
            json.dump(lang_1_to_lang_2_to_tree_dist, f, ensure_ascii=False, indent=4)

    def create_map_cache(self, cache_root="."):
        self.pair_to_map_dist = dict()
        iso_to_long_lat = load_json_from_path(os.path.join(cache_root, "iso_to_long_lat.json"))
        for pair in tqdm(self.pairs):
            try:
                long_1, lat_1 = iso_to_long_lat[pair[0]]
                long_2, lat_2 = iso_to_long_lat[pair[1]]
                geodesic((lat_1, long_1), (lat_2, long_2))
                self.pair_to_map_dist[pair] = geodesic((lat_1, long_1), (lat_2, long_2)).miles
            except KeyError:
                pass
        lang_1_to_lang_2_to_map_dist = dict()
        for pair in self.pair_to_map_dist:
            lang_1 = pair[0]
            lang_2 = pair[1]
            dist = self.pair_to_map_dist[pair]
            if lang_1 not in lang_1_to_lang_2_to_map_dist.keys():
                lang_1_to_lang_2_to_map_dist[lang_1] = dict()
            lang_1_to_lang_2_to_map_dist[lang_1][lang_2] = dist

        with open(os.path.join(cache_root, 'lang_1_to_lang_2_to_map_dist.json'), 'w', encoding='utf-8') as f:
            json.dump(lang_1_to_lang_2_to_map_dist, f, ensure_ascii=False, indent=4)

    def create_oracle_cache(self, model_path, cache_root="."):
        """Oracle language-embedding distance of supervised languages is only used for evaluation, not usable for zero-shot."""
        loss_fn = torch.nn.MSELoss(reduction="mean")
        self.pair_to_lang_emb_dist = dict()
        lang_embs = torch.load(model_path)["model"]["encoder.language_embedding.weight"]
        lang_embs.requires_grad_(False)
        for pair in tqdm(self.pairs):
            try:
                dist = loss_fn(lang_embs[self.iso_lookup[-1][pair[0]]], lang_embs[self.iso_lookup[-1][pair[1]]]).item()
                self.pair_to_lang_emb_dist[pair] = dist
            except KeyError:
                pass
        lang_1_to_lang_2_lang_emb_dist = dict()
        for pair in self.pair_to_lang_emb_dist:
            lang_1 = pair[0]
            lang_2 = pair[1]
            dist = self.pair_to_lang_emb_dist[pair]
            if lang_1 not in lang_1_to_lang_2_lang_emb_dist.keys():
                lang_1_to_lang_2_lang_emb_dist[lang_1] = dict()
            lang_1_to_lang_2_lang_emb_dist[lang_1][lang_2] = dist         
        with open(os.path.join(cache_root, "lang_1_to_lang_2_to_oracle_dist.json"), "w", encoding="utf-8") as f:
            json.dump(lang_1_to_lang_2_lang_emb_dist, f, ensure_ascii=False, indent=4)

    def create_learned_cache(self, model_path, cache_root="."):
        # TODO
        raise NotImplementedError("currently located in MetricMetaLearner.py")

    def create_required_files(self, model_path=None, create_oracle=False):
        if not os.path.exists("lang_1_to_lang_2_to_tree_dist.json"):
            self.create_tree_cache()
        if not os.path.exists("lang_1_to_lang_2_to_map_dist.json"):
            self.create_map_cache()
        if not os.path.exists("lang_1_to_lang_2_to_learned_dist.json"):
            self.create_learned_cache(model_path=args.model_path)
        if not os.path.exists("asp_dict.pkl"):
            raise FileNotFoundError("asp_dict.pkl must be downloaded separately.")
        if create_oracle:
            if not os.path.exists("lang_1_to_lang_2_to_oracle_dist.json"):
                if not model_path:
                    raise ValueError("model_path is required for creating oracle cache.")
                self.create_oracle_cache(model_path=args.model_path)
        print("All required cache files exist.")

def load_json_from_path(path):
    with open(path, "r", encoding="utf8") as f:
        obj = json.loads(f.read())
    return obj


if __name__ == '__main__':
    default_model_path = os.path.join(MODELS_DIR, "ToucanTTS_Meta", "best.pt") # MODELS_DIR must be absolute path, the relative path will fail at this location
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", type=str, default=default_model_path, help="model path that should be used for creating oracle lang emb distance cache")
    args = parser.parse_args()
    cc = CacheCreator()
    cc.create_required_files(args.model_path, create_oracle=True)
