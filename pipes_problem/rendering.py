"""Draw in logical coordinates, rasterize at the window's actual pixel density."""

import pygame


class Canvas:
    def __init__(self, size, scale):
        self.size = size
        self.scale = scale
        self.pixels = pygame.Surface(tuple(round(n * scale) for n in size))

    def get_size(self):
        return self.size

    def get_rect(self):
        return pygame.Rect((0, 0), self.size)

    def fill(self, color):
        self.pixels.fill(color)

    def get_clip(self):
        r = self.pixels.get_clip()
        return pygame.Rect(*(round(v / self.scale) for v in r))

    def set_clip(self, rect):
        self.pixels.set_clip(scaled_rect(rect, self.scale))

    def blit(self, image, position):
        if self.scale != 1:
            image = pygame.transform.smoothscale(
                image, tuple(round(n * self.scale) for n in image.get_size())
            )
        return self.blit_native(image, position)

    def blit_native(self, image, position):
        return self.pixels.blit(image, scaled_point(position, self.scale))


def scaled_point(point, scale):
    return tuple(round(v * scale) for v in point[:2])


def scaled_rect(rect, scale):
    return pygame.Rect(*(round(v * scale) for v in pygame.Rect(rect)))


class SmoothDraw:
    """Supersample primitives at 2x or higher, including on standard displays."""

    def primitive(self, name, target, color, *args, **kwargs):
        if not isinstance(target, Canvas):
            return getattr(pygame.draw, name)(target, color, *args, **kwargs)
        # Small transparent layers avoid redrawing/upscaling the whole screen.
        scale = max(2, target.scale)
        if name in ("rect", "arc"):
            rect = pygame.Rect(args[0])
            bounds = rect.inflate(4, 4)
        elif name == "circle":
            center, radius = args[:2]
            bounds = pygame.Rect(
                center[0] - radius - 2,
                center[1] - radius - 2,
                radius * 2 + 4,
                radius * 2 + 4,
            )
        else:
            points = (
                args[1]
                if name == "lines"
                else args[0]
                if name == "polygon"
                else args[:2]
            )
            xs, ys = zip(*points)
            bounds = pygame.Rect(
                min(xs) - 4, min(ys) - 4, max(xs) - min(xs) + 9, max(ys) - min(ys) + 9
            )
        layer = pygame.Surface(
            (round(bounds.w * scale), round(bounds.h * scale)), pygame.SRCALPHA
        )
        # Keep edge RGB equal to the shape color while filtering alpha. Black
        # transparent pixels otherwise produce dark fringes after interpolation.
        layer.fill((*pygame.Color(color)[:3], 0))

        def point(p):
            return round((p[0] - bounds.x) * scale), round((p[1] - bounds.y) * scale)

        if name == "rect":
            rect = pygame.Rect(args[0]).move(-bounds.x, -bounds.y)
            values = [scaled_rect(rect, scale)]
            if len(args) > 1:
                values.append(round(args[1] * scale))
            kwargs = {k: round(v * scale) for k, v in kwargs.items()}
        elif name == "circle":
            values = [point(args[0]), round(args[1] * scale)]
            if len(args) > 2:
                values.append(round(args[2] * scale))
        elif name == "arc":
            values = [
                scaled_rect(pygame.Rect(args[0]).move(-bounds.x, -bounds.y), scale),
                args[1],
                args[2],
                round(args[3] * scale),
            ]
        elif name == "line":
            values = [
                point(args[0]),
                point(args[1]),
                round((args[2] if len(args) > 2 else 1) * scale),
            ]
        elif name == "lines":
            values = [args[0], [point(p) for p in args[1]], round(args[2] * scale)]
        else:
            values = [[point(p) for p in args[0]]]
        getattr(pygame.draw, name)(layer, color, *values, **kwargs)
        size = round(bounds.w * target.scale), round(bounds.h * target.scale)
        if layer.get_size() != size:
            layer = pygame.transform.smoothscale(layer, size)
        target.blit_native(layer, bounds.topleft)

    def __getattr__(self, name):
        return lambda target, color, *args, **kwargs: self.primitive(
            name, target, color, *args, **kwargs
        )


draw = SmoothDraw()
