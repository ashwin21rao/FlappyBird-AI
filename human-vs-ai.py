import pygame
import random
import collections
import os
import neat
import pickle
import configparser

configParser = configparser.RawConfigParser()
configParser.read("game-config.cfg")

clock = pygame.time.Clock()
FPS = configParser.getint("game settings", "FPS")
screen_width = 800
screen_height = 600
land_thickness = 80

# global variables
g = configParser.getfloat("game settings", "g")
player_speed = configParser.getfloat("game settings", "player_speed")
horizontal_speed = configParser.getfloat("game settings", "horizontal_speed")
distance_between_pipes = configParser.getfloat("game settings", "distance_between_pipes")
horizontal_distance_between_pipes = screen_width / configParser.getfloat("game settings", "horizontal_distance_between_pipes")
min_pipe_height = configParser.getfloat("game settings", "min_pipe_height")
scores = [0, 0]

# sprites and sprite groups
obstacles = pygame.sprite.LayeredUpdates()
surfaces = []
players = []
pipes = collections.deque()
passed_pipes = collections.deque()

# global variables for NEAT
neural_network = None  # neural networks for AI
HUMAN_PLAYER = True


class Player(pygame.sprite.Sprite):

    def __init__(self, x_coordinate, y_coordinate, speed, player_images, is_human):
        super(Player, self).__init__()
        self._layer = 0
        self.score = 0
        self.x_coordinate = x_coordinate
        self.y_coordinate = y_coordinate
        self.speed_on_press = -speed
        self.speed = 0
        self.time_since_press = 0
        self.time_of_press = pygame.time.get_ticks()  # start time
        self.pressed = False
        self.is_human = is_human

        self.animation_time = FPS / 3  # 3 animations every second
        self.animation_frame_count = 0  # counts number of frames passed

        self.images = player_images
        self.surface = self.images[2]
        self.rect = self.surface.get_rect(center=(self.x_coordinate, self.y_coordinate))

    def runMotionEngine(self):
        self.speed = self.speed_on_press + g * self.time_since_press
        self.y_coordinate += self.speed_on_press * self.time_since_press + 0.5 * g * self.time_since_press ** 2

    def movePlayerOnScreen(self, flap_sound, output=0):

        if self.is_human:
            # movement of player on press (hold not allowed)
            keys = pygame.key.get_pressed()
            if keys[pygame.K_UP] and not self.pressed:
                flap_sound.play()
                self.rect.move_ip(0, self.speed_on_press)
                self.time_since_press = 0
                self.time_of_press = pygame.time.get_ticks()
                self.pressed = True

            else:
                self.rect.move_ip(0, self.speed)
                self.time_since_press = (pygame.time.get_ticks() - self.time_of_press) / 1000
                if not keys[pygame.K_UP]:
                    self.pressed = False

        else:
            # movement of player based on output of neural network
            if output > 0.5:
                self.rect.move_ip(0, self.speed_on_press)
                self.time_since_press = 0
                self.time_of_press = pygame.time.get_ticks()

            else:
                self.rect.move_ip(0, self.speed)
                self.time_since_press = (pygame.time.get_ticks() - self.time_of_press) / 1000

        self.animatePlayer()

        # prevent player from going off screen
        if self.rect.top < 0:
            self.rect.top = 0
        if self.rect.bottom > screen_height:
            self.rect.bottom = screen_height

    def animatePlayer(self):
        self.animation_frame_count += 1
        if self.animation_frame_count < self.animation_time / 4:
            self.surface = self.images[0]
        elif self.animation_frame_count < 2 * self.animation_time / 4:
            self.surface = self.images[1]
        elif self.animation_frame_count < 3 * self.animation_time / 4:
            self.surface = self.images[2]
        elif self.animation_frame_count < self.animation_time:
            self.surface = self.images[1]
        else:
            self.animation_frame_count = 0


class Land(pygame.sprite.Sprite):
    def __init__(self, position, land_image):
        super(Land, self).__init__()
        self._layer = 2
        self.position = position
        self.surface = land_image

        if self.position == "top":
            self.surface = pygame.transform.flip(self.surface, False, True)
            self.rect = self.surface.get_rect(center=(screen_width, land_thickness / 2))
        if self.position == "bottom":
            self.rect = self.surface.get_rect(center=(screen_width, screen_height - land_thickness / 2))

    def moveHorizontal(self):
        self.rect.move_ip(-horizontal_speed, 0)


class Pipes(pygame.sprite.Sprite):
    def __init__(self, position, top_coordinate, pipe_image):
        super(Pipes, self).__init__()
        self._layer = 1
        self.position = position
        self.surface = pipe_image

        if self.position == "top":
            self.top_coordinate = top_coordinate
            self.surface = pygame.transform.flip(self.surface, False, True)
            self.rect = self.surface.get_rect(midbottom=(screen_width + 100, self.top_coordinate))
        if self.position == "bottom":
            self.top_coordinate = top_coordinate + distance_between_pipes
            self.rect = self.surface.get_rect(midtop=(screen_width + 100, self.top_coordinate))

    def moveHorizontal(self):
        self.rect.move_ip(-horizontal_speed, 0)


def displayInfo(screen, font):
    text_surface = font.render(f"Player Score: {scores[0]}", False, (0, 0, 0))
    screen.blit(text_surface, (5, 3))

    text_surface = font.render(f"AI Score: {scores[1]}", False, (0, 0, 0))
    screen.blit(text_surface, (5, 33))


def displaySprites(screen, background):
    screen.blit(background, (0, 0))
    for obstacle in obstacles:
        screen.blit(obstacle.surface, obstacle.rect)
    displayPlayers(screen)


def displayPlayers(screen):
    for player in players:
        rotated_image = pygame.transform.rotate(player.surface, (-25 if player.speed > 0 else 25))
        new_rect = rotated_image.get_rect(center=player.surface.get_rect(topleft=player.rect.topleft).center)
        screen.blit(rotated_image, new_rect)


def createPlayers(winner, config, player1_images, player2_images):
    # create neural network for best genome
    global neural_network
    neural_network = neat.nn.RecurrentNetwork.create(winner, config)

    # create player for best genome
    player = Player(screen_width / 3, screen_height / 2, player_speed, player1_images, False)
    players.append(player)

    if HUMAN_PLAYER:
        # create player for human
        player = Player(screen_width / 3, screen_height / 2, player_speed, player2_images, True)
        players.append(player)


def createSurfaces(land_image):
    top_surface = Land("top", land_image)
    bottom_surface = Land("bottom", land_image)
    obstacles.add(top_surface), surfaces.append(top_surface)
    obstacles.add(bottom_surface), surfaces.append(bottom_surface)


def createPipes(pipe_image):
    top_coordinate = random.randint(land_thickness + min_pipe_height,
                                    screen_height - land_thickness - min_pipe_height - distance_between_pipes)
    top_pipe = Pipes("top", top_coordinate, pipe_image)
    bottom_pipe = Pipes("bottom", top_coordinate, pipe_image)
    obstacles.add(top_pipe), pipes.append(top_pipe)
    obstacles.add(bottom_pipe), pipes.append(bottom_pipe)


def moveObstacles(pipe_image, land_image):
    for obstacle in obstacles:
        obstacle.moveHorizontal()

    if screen_width - pipes[-1].rect.right > screen_width / 7:
        createPipes(pipe_image)
    if len(passed_pipes) > 0 and passed_pipes[0].rect.right < 0:
        passed_pipes[0].kill()
        passed_pipes[1].kill()
        passed_pipes.popleft(), passed_pipes.popleft()

    if surfaces[0].rect.right <= screen_width:
        surfaces[0].kill()
        surfaces[1].kill()
        surfaces.clear()
        createSurfaces(land_image)


def checkCollision(player, index):
    collided = pygame.sprite.spritecollideany(player, obstacles, collided=pygame.sprite.collide_rect_ratio(0.95))
    if collided:
        player.kill()
        players.pop(index)  # remove player

    return collided


def calculateScore():
    if pipes[0].rect.right < players[0].rect.left:
        for index, player in enumerate(players):
            player.score += 1
            scores[0 if player.is_human else 1] = player.score

        passed_pipes.append(pipes.popleft())
        passed_pipes.append(pipes.popleft())


def feedIntoNeuralNetwork(player):
    # pass input into neural network
    # 1) y coordinate of player
    # 2) horizontal distance from nearest pipe
    # 3) vertical distance from top pipe
    # 4) vertical distance from bottom pipe

    output = neural_network.activate(
        (player.y_coordinate / 200,
         abs(player.rect.centerx - pipes[0].rect.centerx) / 100,
         abs(player.rect.centery - pipes[0].rect.bottom) / 100,
         abs(player.rect.centery - pipes[1].rect.top) / 100))

    return output[0]


def initializeGame():
    pygame.mixer.pre_init(44100, -16, 2, 2048)
    pygame.mixer.init()
    pygame.init()
    pygame.mixer.music.load("extras/backgroundmusic.wav")
    pygame.mixer.music.play(loops=-1)
    pygame.font.init()

    screen = pygame.display.set_mode((screen_width, screen_height))
    background = pygame.image.load("extras/background.png")
    background = pygame.transform.scale(background, (screen_width, screen_height))

    pygame.display.set_caption("Flappy Bird")
    icon = pygame.image.load("extras/bird2.png").convert_alpha()
    pygame.display.set_icon(icon)

    return screen, background


def loadExtras():
    player1_images = [pygame.image.load("extras/bird1.png").convert(),
                      pygame.image.load("extras/bird2.png").convert(),
                      pygame.image.load("extras/bird3.png").convert()]
    player2_images = [pygame.image.load("extras/bluebird1.png").convert_alpha(),
                      pygame.image.load("extras/bluebird2.png").convert_alpha(),
                      pygame.image.load("extras/bluebird3.png").convert_alpha()]
    land_image = pygame.image.load("extras/base.png").convert()
    land_image = pygame.transform.scale(land_image, (screen_width * 2, land_thickness))
    pipe_image = pygame.image.load("extras/pipe.png").convert()

    game_font = pygame.font.Font("extras/roboto-bold.ttf", 25)
    flap_sound = pygame.mixer.Sound("extras/flapsound.wav")

    images = {"player1": player1_images,
              "player2": player2_images,
              "land": land_image,
              "pipe": pipe_image}

    return images, game_font, flap_sound


def gameloop(best_genome, config):
    screen, background = initializeGame()
    images, font, flap_sound = loadExtras()

    createPipes(images["pipe"])
    createSurfaces(images["land"])
    createPlayers(best_genome, config, images["player1"], images["player2"])

    running = True
    while running:

        # check for events
        for event in pygame.event.get():

            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

        # display sprites
        displaySprites(screen, background)
        displayInfo(screen, font)

        # move obstacles
        moveObstacles(images["pipe"], images["land"])

        # calculate scores
        calculateScore()

        # perform operations on each player
        for index, player in enumerate(players):
            player.runMotionEngine()

            if index == 0:
                output = feedIntoNeuralNetwork(player)
                player.movePlayerOnScreen(flap_sound, output)
            else:
                player.movePlayerOnScreen(flap_sound)

            # calculateScore(player, index)
            checkCollision(player, index)

        # quit generation once all players die
        if len(players) == 0:
            running = False

        # update the display
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


# set up NEAT algorithm
def runNeatAlgorithm(config_path):
    # set up NEAT configuration from config file
    config = neat.config.Config(neat.DefaultGenome, neat.DefaultReproduction,
                                neat.DefaultSpeciesSet, neat.DefaultStagnation, config_path)

    # load trained AI
    file = open("models/trained-model1.pickle", "rb")
    best_genome = pickle.load(file)
    file.close()

    gameloop(best_genome, config)


if __name__ == "__main__":
    local_dir = os.path.dirname(__file__)
    path_to_config_file = os.path.join(local_dir, "neat-config.cfg")
    runNeatAlgorithm(path_to_config_file)
