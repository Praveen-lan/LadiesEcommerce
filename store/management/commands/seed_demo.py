import random
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from store.models import Banner, Category, DEFAULT_SUBCATEGORIES, Saree, SiteSettings, SubCategory

try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None


HD = {
    "saree": (1400, 1867),
    "banner": (2560, 1000),
    "category": (1600, 640),
    "logo": (512, 512),
}

PALETTES = {
    "high": {
        "name": "Luxury Pure Silk",
        "subtitle": "Handwoven Banarasi & Kanchipuram silks for brides and grand occasions",
        "colors": ["#8e1f3d", "#5c1230", "#b04018", "#3e2a55", "#a61f1f", "#6d1b45"],
        "names": ["Banarasi Kumkum Silk", "Kanchipuram Temple Border", "Mysore Royal Silver Zari", "Patola Heritage Silk", "Banarasi Moonlight Brocade", "Kanjivaram Antique Gold"],
    },
    "medium": {
        "name": "Premium Collection",
        "subtitle": "Soft chiffons, satins and georgettes — festive favourites",
        "colors": ["#0f4c5c", "#2c6e63", "#7a4b8c", "#b08a2e", "#3f6d9c", "#2f7050"],
        "names": ["Chiffon Sunset Saree", "Georgette Midnight Bloom", "Satin Peacock Trail", "Crepe Emerald Shimmer", "Organza Festive Waves", "Soft Silk Party Saree"],
    },
    "basic": {
        "name": "Everyday Comfort",
        "subtitle": "Lightweight cottons and linens for daily elegance",
        "colors": ["#b26b3c", "#4f6d7a", "#8a7a54", "#a0503a", "#5d6d8c", "#6d7a4a"],
        "names": ["Cotton Linen Classics", "e.co Plain Cotton", "Handloom Weave Wrap", "Kora Cotton Everyday", "Checkered Daily Saree", "Cottage Cotton Comfort"],
    },
}


def make_image(colors, size, label="", stripes=False):
    if Image is None:
        return None
    width, height = size
    img = Image.new("RGB", (width, height), colors[0])
    draw = ImageDraw.Draw(img)

    steps = len(colors)
    for i, color in enumerate(colors):
        y0 = int(height * i / steps)
        y1 = int(height * (i + 1) / steps)
        draw.rectangle([0, y0, width, y1], fill=color)

    if stripes:
        for _ in range(random.randint(3, 6)):
            thickness = random.randint(width // 28, width // 12)
            x = random.randint(width // 6, width - width // 6)
            draw.line([(x, 0), (x - width // 4, height)], fill=(255, 255, 255), width=thickness)

    if label:
        try:
            from PIL import ImageFont

            font = ImageFont.truetype("arial.ttf", max(width // 28, 24))
        except Exception:
            font = ImageFont.load_default()
        band_h = int(height * 0.12)
        draw.rectangle([0, height - band_h, width, height], fill=colors[-1])
        draw.text((int(width * 0.04), height - band_h + int(band_h * 0.22)), label, fill=(255, 255, 255), font=font)
    return img


def make_saree_image(colors, size, label="", variant=0):
    """Generate a realistic-looking saree with a layout unique to each variant."""
    if Image is None:
        return None
    width, height = size
    rng = random.Random(variant * 7919)

    rotated = colors[(variant % len(colors)):] + colors[:(variant % len(colors))]
    img = Image.new("RGB", (width, height), rotated[0])
    draw = ImageDraw.Draw(img)

    steps = len(rotated)
    for i, color in enumerate(rotated):
        y0 = int(height * i / steps)
        y1 = int(height * (i + 1) / steps)
        draw.rectangle([0, y0, width, y1], fill=color)

    # pleat folds - soft waves (horizontal or diagonal per variant)
    from PIL import ImageFilter

    diag = variant % 2 == 0
    for j, y in enumerate(range(int(height * 0.15), int(height * 0.72), int(height * 0.030))):
        shade = (255, 255, 255) if (variant + j) % 3 else (0, 0, 0)
        pts = []
        step = max(width // 22, 8)
        for x in range(-step, width + step, step):
            offset = int((x % (step * 3)) / step) * 7 - 12 if not diag else int((x % (step * 2)) / step) * 5 - 8
            pts.append((x, y + offset))
        draw.line(pts, fill=shade, width=max(2, width // 230))

    # gold / silver zari border at bottom
    gold = [(212, 175, 55), (232, 205, 120)] if variant % 3 else [(196, 196, 200), (226, 226, 230)]
    b1 = int(height * 0.80)
    b2 = int(height * 0.84)
    draw.rectangle([0, b1, width, b2], fill=gold[0])
    draw.rectangle([0, b2, width, b2 + int(height * 0.02)], fill=gold[1])

    # pallu band on left or right side
    band_w = max(8, width // 55)
    if variant % 2 == 0:
        px = width - int(width * 0.18)
        draw.rectangle([px, 0, px + band_w, height], fill=gold[0])
        draw.rectangle([px - band_w, int(height * 0.6), px, height], fill=gold[1])
    else:
        px = int(width * 0.12)
        draw.rectangle([px - band_w, 0, px, height], fill=gold[0])
        draw.rectangle([px, int(height * 0.55), px + band_w, height], fill=(gold[1][0] // 2 * 2, gold[1][1] // 2 * 2, gold[1][2] // 2 * 2))

    # motif: scattered dots or floral clusters unique per variant
    if variant % 4 < 3:
        for _ in range(rng.randint(18, 34)):
            dot_x = rng.randint(int(width * 0.16), width - int(width * 0.04))
            dot_y = rng.randint(b1 - int(height * 0.07), b1 - 4)
            r = rng.randint(2, 6)
            draw.ellipse([dot_x - r, dot_y - r, dot_x + r, dot_y + r], fill=gold[1])
    else:
        cx, cy = rng.randint(width // 5, width - width // 5), rng.randint(int(height * 0.45), int(height * 0.6))
        for r in (8, 14, 20):
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=gold[1], width=3)

    img = img.filter(ImageFilter.GaussianBlur(0.4))

    if label:
        try:
            from PIL import ImageFont

            font = ImageFont.truetype("arial.ttf", max(width // 32, 20))
        except Exception:
            font = ImageFont.load_default()
        label_h = int(height * 0.09)
        overlay = Image.new("RGBA", (width, label_h), (6, 43, 30, 200))
        img.paste(overlay, (0, height - label_h), overlay)
        d2 = ImageDraw.Draw(img)
        d2.text((int(width * 0.04), height - label_h + int(label_h * 0.3)), label, fill=(255, 255, 255), font=font)
    return img


def save_image(img, name):
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return ContentFile(buf.getvalue(), name=name)


class Command(BaseCommand):
    help = "Generate demo categories, sarees, banners and site settings (HD images)."

    def add_arguments(self, parser):
        parser.add_argument("--refresh-images", action="store_true", help="Re-generate HD images for existing records.")

    @transaction.atomic
    def handle(self, *args, **options):
        refresh = options["refresh_images"]
        Path("media").mkdir(exist_ok=True)

        site = SiteSettings.objects.first()
        if site and not refresh:
            self.stdout.write("Site settings already exist.")
        else:
            if not site:
                site = SiteSettings(
                    shop_name="Saree Elegance",
                    tagline="A curated haven of handwoven silk, chiffon and cotton sarees — crafted to celebrate every moment of your life.",
                    phone="9876543210",
                    email="hello@sareeelegance.in",
                    address="18, Heritage Textile Street, Anna Nagar, Chennai, Tamil Nadu 600040",
                    whatsapp="919876543210",
                    facebook="https://facebook.com/sareeelegance",
                    instagram="https://instagram.com/sareeelegance",
                    twitter="https://twitter.com/sareeelegance",
                    youtube="https://youtube.com/@sareeelegance",
                )
            site.logo = save_image(make_image(["#0e5c3f", "#062b1e"], HD["logo"], "", False), "logo.png")
            site.save()
            self.stdout.write(self.style.SUCCESS("Site settings Logo regenerated."))

        tiers = ["high", "medium", "basic"]
        for tier in tiers:
            cat = Category.objects.filter(tier=tier).first()
            if cat and not refresh:
                continue
            if not cat:
                pal = PALETTES[tier]
                cat = Category(title=pal["name"], tier=tier, subtitle=pal["subtitle"], order=tiers.index(tier))
            cat.image = save_image(make_image(PALETTES[tier]["colors"][:2] + ["#000000"], HD["category"], PALETTES[tier]["name"], True), f"cat_{tier}.png")
            cat.save()
            self.stdout.write(self.style.SUCCESS(f"Category image for '{cat.title}' set."))

            for position, (title, subtitle, keywords) in enumerate(DEFAULT_SUBCATEGORIES):
                SubCategory.objects.get_or_create(
                    category=cat,
                    title=title,
                    defaults={"subtitle": subtitle, "order": position},
                )
            self.stdout.write(self.style.SUCCESS(f"{len(DEFAULT_SUBCATEGORIES)} sub categories created for '{cat.title}'."))

        for tier_index, (tier, pal) in enumerate(PALETTES.items()):
            cat = Category.objects.get(tier=tier)
            created = 0
            for idx, name in enumerate(pal["names"]):
                slug = slugify(name)
                saree = Saree.objects.filter(slug=slug, category=cat).first()
                if saree and not refresh:
                    continue
                if not saree:
                    mrp = random.choice([1299, 1599, 1899, 2199, 2499, 2999, 3499])
                    price = int(mrp * random.uniform(0.55, 0.8))
                    saree = Saree(
                        category=cat,
                        name=name,
                        slug=slug,
                        price=price,
                        mrp=mrp,
                        fabric="Silk" if tier == "high" else ("Georgette" if tier == "medium" else "Cotton"),
                        description=f"A beautiful {pal['name'].lower()} saree with a refined finish, perfect for every occasion.",
                        is_featured=idx < 3,
                    )
                saree.image = save_image(make_saree_image(pal["colors"], HD["saree"], name, variant=idx + tier_index * 7), f"{tier}_{idx}.png")
                saree.save()
                created += 1
            self.stdout.write(self.style.SUCCESS(f"{created} HD saree images generated for '{pal['name']}'."))

        banner_data = [
            ("Endless Festive Elegance", "Grand Collection — pure silks & handwoven treasures", "Heritage Silk Festival", ["#0e5c3f", "#062b1e", "#000000"]),
            ("New Season, New You", "Premium chiffons & soft georgettes now in store", "Shop Premium", ["#0f4c3a", "#062a1e", "#000000"]),
            ("Everyday Comfort Begins Here", "Lightweight cottons for your everyday grace", "Explore Everyday", ["#b04018", "#5c2412", "#000000"]),
        ]
        for i, (title, subtitle, label, colors) in enumerate(banner_data):
            banner = Banner.objects.filter(order=i).first()
            if banner and not refresh:
                continue
            if not banner:
                banner = Banner(title=title, subtitle=subtitle, order=i, is_active=True)
            banner.image = save_image(make_image(colors, HD["banner"], label, True), f"banner_{i + 1}.png")
            banner.save()
        self.stdout.write(self.style.SUCCESS("3 HD banners regenerated."))

        self.stdout.write(self.style.SUCCESS("Seed complete."))