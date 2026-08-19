import datetime
from dateutil import relativedelta
import requests
import os
from lxml import etree
import time
import hashlib



USER_NAME = "hasnainzaheer48-beep"

ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")

if not ACCESS_TOKEN:
    raise RuntimeError(
        "ACCESS_TOKEN environment variable is not set."
    )

HEADERS = {
    "Authorization": "Bearer " + ACCESS_TOKEN,
    "Content-Type": "application/json",
}

# Optional:
# Set this if you want your age displayed in the SVG.
#
# PowerShell:
# $env:BIRTHDAY="2006-08-15"
#
# If not provided, age_data will display "N/A".
BIRTHDAY = os.environ.get("BIRTHDAY")


QUERY_COUNT = {
    "user_getter": 0,
    "follower_getter": 0,
    "graph_repos_stars": 0,
    "recursive_loc": 0,
    "graph_commits": 0,
    "loc_query": 0,
}




def daily_readme(birthday):
    """
    Returns the length of time since birth.

    Example:
    20 years, 2 months, 4 days
    """

    diff = relativedelta.relativedelta(
        datetime.datetime.today(),
        birthday
    )

    return "{} {}, {} {}, {} {}{}".format(
        diff.years,
        "year" + format_plural(diff.years),

        diff.months,
        "month" + format_plural(diff.months),

        diff.days,
        "day" + format_plural(diff.days),

        " 🎂"
        if diff.months == 0 and diff.days == 0
        else ""
    )


def format_plural(unit):
    """
    Returns 's' when a value is not 1.
    """

    return "s" if unit != 1 else ""


def simple_request(func_name, query, variables):
    """
    Sends a GitHub GraphQL request.
    """

    request = requests.post(
        "https://api.github.com/graphql",
        json={
            "query": query,
            "variables": variables
        },
        headers=HEADERS,
        timeout=30
    )

    if request.status_code != 200:
        raise Exception(
            func_name,
            "has failed with",
            request.status_code,
            request.text,
            QUERY_COUNT
        )

    response = request.json()

    if "errors" in response:
        raise Exception(
            func_name,
            "GraphQL error:",
            response["errors"]
        )

    return request


def graph_commits(start_date, end_date):
    """
    Returns GitHub contribution count between two dates.
    """

    query_count("graph_commits")

    query = """
    query(
        $start_date: DateTime!,
        $end_date: DateTime!,
        $login: String!
    ) {
        user(login: $login) {
            contributionsCollection(
                from: $start_date,
                to: $end_date
            ) {
                contributionCalendar {
                    totalContributions
                }
            }
        }
    }
    """

    variables = {
        "start_date": start_date,
        "end_date": end_date,
        "login": USER_NAME
    }

    request = simple_request(
        graph_commits.__name__,
        query,
        variables
    )

    return int(
        request.json()["data"]["user"]
        ["contributionsCollection"]
        ["contributionCalendar"]
        ["totalContributions"]
    )



def graph_repos_stars(
    count_type,
    owner_affiliation,
    cursor=None
):
    """
    Returns repository count or total stars.
    """

  
    if count_type == "repos":

        query_count("graph_repos_stars")

        query = """
        query(
            $owner_affiliation: [RepositoryAffiliation],
            $login: String!
        ) {
            user(login: $login) {

                repositories(
                    first: 100,
                    ownerAffiliations: $owner_affiliation
                ) {
                    totalCount
                }
            }
        }
        """

        variables = {
            "owner_affiliation": owner_affiliation,
            "login": USER_NAME
        }

        request = simple_request(
            graph_repos_stars.__name__,
            query,
            variables
        )

        repositories = (
            request.json()["data"]["user"]["repositories"]
        )

        return repositories["totalCount"]

 

    elif count_type == "stars":

        total_stars = 0
        page = 1

        while True:

            request = requests.get(
                "https://api.github.com/user/repos",
                headers={
                    "Authorization": "Bearer " + ACCESS_TOKEN,
                    "Accept": "application/vnd.github+json"
                },
                params={
                    "per_page": 100,
                    "page": page,
                    "affiliation": "owner"
                },
                timeout=30
            )

            if request.status_code != 200:

                raise Exception(
                    "Failed to fetch repositories:",
                    request.status_code,
                    request.text
                )

            repositories = request.json()

            if not repositories:
                break

            for repository in repositories:

                total_stars += repository.get(
                    "stargazers_count",
                    0
                )

            if len(repositories) < 100:
                break

            page += 1

        return total_stars

    return 0



def recursive_loc(
    owner,
    repo_name,
    data,
    cache_comment,
    addition_total=0,
    deletion_total=0,
    my_commits=0,
    cursor=None
):
    """
    Fetches repository commits using GraphQL pagination.
    """

    query_count("recursive_loc")

    query = """
    query(
        $repo_name: String!,
        $owner: String!,
        $cursor: String
    ) {
        repository(
            name: $repo_name,
            owner: $owner
        ) {
            defaultBranchRef {
                target {
                    ... on Commit {

                        history(
                            first: 100,
                            after: $cursor
                        ) {

                            totalCount

                            edges {
                                node {

                                    ... on Commit {
                                        committedDate
                                    }

                                    author {
                                        user {
                                            id
                                        }
                                    }

                                    deletions
                                    additions
                                }
                            }

                            pageInfo {
                                endCursor
                                hasNextPage
                            }
                        }
                    }
                }
            }
        }
    }
    """

    variables = {
        "repo_name": repo_name,
        "owner": owner,
        "cursor": cursor
    }

    request = requests.post(
        "https://api.github.com/graphql",
        json={
            "query": query,
            "variables": variables
        },
        headers=HEADERS,
        timeout=30
    )

    if request.status_code == 200:

        repository = request.json()["data"]["repository"]

        if repository is None:
            return (
                addition_total,
                deletion_total,
                my_commits
            )

        branch = repository["defaultBranchRef"]

        if branch is None:
            return 0

        return loc_counter_one_repo(
            owner,
            repo_name,
            data,
            cache_comment,
            branch["target"]["history"],
            addition_total,
            deletion_total,
            my_commits
        )

    force_close_file(
        data,
        cache_comment
    )

    if request.status_code == 403:
        raise Exception(
            "Too many GitHub API requests."
        )

    raise Exception(
        "recursive_loc() failed with",
        request.status_code,
        request.text,
        QUERY_COUNT
    )


def loc_counter_one_repo(
    owner,
    repo_name,
    data,
    cache_comment,
    history,
    addition_total,
    deletion_total,
    my_commits
):
    """
    Counts additions/deletions from commits authored by us.
    """

    for edge in history["edges"]:

        node = edge["node"]

        author = node.get("author")

        if not author:
            continue

        user = author.get("user")

        if not user:
            continue

        if user["id"] == OWNER_ID:

            my_commits += 1

            addition_total += node["additions"]

            deletion_total += node["deletions"]

    if (
        not history["edges"]
        or not history["pageInfo"]["hasNextPage"]
    ):
        return (
            addition_total,
            deletion_total,
            my_commits
        )

    return recursive_loc(
        owner,
        repo_name,
        data,
        cache_comment,
        addition_total,
        deletion_total,
        my_commits,
        history["pageInfo"]["endCursor"]
    )



def loc_query(
    owner_affiliation,
    comment_size=0,
    force_cache=False,
    cursor=None,
    edges=None
):
    """
    Gets repositories and checks their commit history.
    """

    query_count("loc_query")

    if edges is None:
        edges = []

    query = """
    query(
        $owner_affiliation: [RepositoryAffiliation],
        $login: String!,
        $cursor: String
    ) {

        user(login: $login) {

            repositories(
                first: 60,
                after: $cursor,
                ownerAffiliations: $owner_affiliation
            ) {

                edges {

                    node {

                        nameWithOwner

                        defaultBranchRef {

                            target {

                                ... on Commit {

                                    history {
                                        totalCount
                                    }
                                }
                            }
                        }
                    }
                }

                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }
    """

    variables = {
        "owner_affiliation": owner_affiliation,
        "login": USER_NAME,
        "cursor": cursor
    }

    request = simple_request(
        loc_query.__name__,
        query,
        variables
    )

    repositories = (
        request.json()["data"]["user"]["repositories"]
    )

    edges.extend(repositories["edges"])

    if repositories["pageInfo"]["hasNextPage"]:

        return loc_query(
            owner_affiliation,
            comment_size,
            force_cache,
            repositories["pageInfo"]["endCursor"],
            edges
        )

    return cache_builder(
        edges,
        comment_size,
        force_cache
    )



def cache_builder(
    edges,
    comment_size,
    force_cache,
    loc_add=0,
    loc_del=0
):
    """
    Updates LOC only for repositories whose commit count changed.
    """

    cached = True

    os.makedirs("cache", exist_ok=True)

    filename = (
        "cache/"
        + hashlib.sha256(
            USER_NAME.encode("utf-8")
        ).hexdigest()
        + ".txt"
    )

    try:

        with open(filename, "r") as f:
            data = f.readlines()

    except FileNotFoundError:

        data = []

        if comment_size > 0:

            for _ in range(comment_size):

                data.append(
                    "This line is a comment block.\n"
                )

        with open(filename, "w") as f:
            f.writelines(data)

    if (
        len(data) - comment_size != len(edges)
        or force_cache
    ):

        cached = False

        flush_cache(
            edges,
            filename,
            comment_size
        )

        with open(filename, "r") as f:
            data = f.readlines()

    cache_comment = data[:comment_size]

    data = data[comment_size:]

    for index in range(len(edges)):

        repo_hash, commit_count, *__ = data[index].split()

        current_hash = hashlib.sha256(
            edges[index]["node"]
            ["nameWithOwner"]
            .encode("utf-8")
        ).hexdigest()

        if repo_hash != current_hash:
            continue

        branch = (
            edges[index]["node"]
            ["defaultBranchRef"]
        )

        if branch is None:

            data[index] = (
                repo_hash
                + " 0 0 0 0\n"
            )

            continue

        current_commit_count = (
            branch["target"]
            ["history"]
            ["totalCount"]
        )

        if int(commit_count) != current_commit_count:

            owner, repo_name = (
                edges[index]["node"]
                ["nameWithOwner"]
                .split("/", 1)
            )

            loc = recursive_loc(
                owner,
                repo_name,
                data,
                cache_comment
            )

            data[index] = (
                repo_hash
                + " "
                + str(current_commit_count)
                + " "
                + str(loc[2])
                + " "
                + str(loc[0])
                + " "
                + str(loc[1])
                + "\n"
            )

            cached = False

    with open(filename, "w") as f:

        f.writelines(cache_comment)
        f.writelines(data)

    for line in data:

        loc = line.split()

        loc_add += int(loc[3])
        loc_del += int(loc[4])

    return [
        loc_add,
        loc_del,
        loc_add - loc_del,
        cached
    ]


def flush_cache(
    edges,
    filename,
    comment_size
):
    """
    Resets repository cache.
    """

    data = []

    try:

        with open(filename, "r") as f:

            if comment_size > 0:
                data = f.readlines()[:comment_size]

    except FileNotFoundError:
        pass

    with open(filename, "w") as f:

        f.writelines(data)

        for node in edges:

            repo_hash = hashlib.sha256(
                node["node"]
                ["nameWithOwner"]
                .encode("utf-8")
            ).hexdigest()

            f.write(
                repo_hash
                + " 0 0 0 0\n"
            )


def force_close_file(
    data,
    cache_comment
):
    """
    Saves partial cache if LOC calculation fails.
    """

    os.makedirs("cache", exist_ok=True)

    filename = (
        "cache/"
        + hashlib.sha256(
            USER_NAME.encode("utf-8")
        ).hexdigest()
        + ".txt"
    )

    with open(filename, "w") as f:

        f.writelines(cache_comment)
        f.writelines(data)

    print(
        "Partial cache saved to:",
        filename
    )



def commit_counter(comment_size):
    """
    Counts commits authored by the user.
    """

    filename = (
        "cache/"
        + hashlib.sha256(
            USER_NAME.encode("utf-8")
        ).hexdigest()
        + ".txt"
    )

    with open(filename, "r") as f:
        data = f.readlines()

    data = data[comment_size:]

    total_commits = 0

    for line in data:

        parts = line.split()

        if len(parts) >= 3:

            total_commits += int(parts[2])

    return total_commits



def user_getter(username):
    """
    Gets GitHub user ID and account creation date.
    """

    query_count("user_getter")

    query = """
    query($login: String!) {

        user(login: $login) {

            id
            createdAt
        }
    }
    """

    request = simple_request(
        user_getter.__name__,
        query,
        {"login": username}
    )

    user = request.json()["data"]["user"]

    return (
    user["id"],
    user["createdAt"]
)


def follower_getter(username):
    """
    Gets GitHub follower count.
    """

    query_count("follower_getter")

    query = """
    query($login: String!) {

        user(login: $login) {

            followers {
                totalCount
            }
        }
    }
    """

    request = simple_request(
        follower_getter.__name__,
        query,
        {"login": username}
    )

    return int(
        request.json()["data"]["user"]
        ["followers"]
        ["totalCount"]
    )



def svg_overwrite(
    filename,
    age_data,
    commit_data,
    star_data,
    repo_data,
    contrib_data,
    follower_data,
    loc_data
):
    """
    Updates the SVG using IDs.
    """

    tree = etree.parse(filename)

    root = tree.getroot()

    justify_format(
        root,
        "commit_data",
        commit_data,
        22
    )

    justify_format(
        root,
        "star_data",
        star_data,
        14
    )

    justify_format(
        root,
        "repo_data",
        repo_data,
        6
    )

    justify_format(
        root,
        "contrib_data",
        contrib_data
    )

    justify_format(
        root,
        "follower_data",
        follower_data,
        10
    )

    justify_format(
        root,
        "loc_data",
        loc_data[2],
        9
    )

    justify_format(
        root,
        "loc_add",
        loc_data[0]
    )

    justify_format(
        root,
        "loc_del",
        loc_data[1],
        7
    )

    justify_format(
        root,
        "age_data",
        age_data,
        30
    )

    tree.write(
        filename,
        encoding="utf-8",
        xml_declaration=True
    )


def justify_format(
    root,
    element_id,
    new_text,
    length=0
):
    """
    Updates SVG text and adjusts preceding dots.
    """

    if isinstance(new_text, int):

        new_text = "{:,}".format(new_text)

    new_text = str(new_text)

    find_and_replace(
        root,
        element_id,
        new_text
    )

    just_len = max(
        0,
        length - len(new_text)
    )

    if just_len <= 2:

        dot_map = {
            0: "",
            1: " ",
            2: ". "
        }

        dot_string = dot_map[just_len]

    else:

        dot_string = (
            " "
            + "." * just_len
            + " "
        )

    find_and_replace(
        root,
        element_id + "_dots",
        dot_string
    )


def find_and_replace(
    root,
    element_id,
    new_text
):
    """
    Finds an SVG element by ID and changes its text.
    """

    element = root.find(
        ".//*[@id='{}']".format(element_id)
    )

    if element is not None:

        element.text = str(new_text)




def query_count(function_id):

    global QUERY_COUNT

    QUERY_COUNT[function_id] += 1




def perf_counter(function, *args):

    start = time.perf_counter()

    result = function(*args)

    return (
        result,
        time.perf_counter() - start
    )


def formatter(
    query_type,
    difference
):
    """
    Prints execution time.
    """

    print(
        "{:<23}".format(
            "   " + query_type + ":"
        ),
        end=""
    )

    if difference > 1:

        print(
            "{:>12}".format(
                "%.4f" % difference + " s"
            )
        )

    else:

        print(
            "{:>12}".format(
                "%.4f" % (difference * 1000)
                + " ms"
            )
        )




if __name__ == "__main__":

    print()
    print("GitHub README Generator")
    print("=======================")
    print()
    print("User:", USER_NAME)
    print()

 

    user_data, user_time = perf_counter(
        user_getter,
        USER_NAME
    )

    OWNER_ID, acc_date = user_data

    formatter(
        "account data",
        user_time
    )

   

    if BIRTHDAY:

        birthday = datetime.datetime.strptime(
            BIRTHDAY,
            "%Y-%m-%d"
        )

        age_data, age_time = perf_counter(
            daily_readme,
            birthday
        )

    else:

        age_data = "N/A"
        age_time = 0

    formatter(
        "age calculation",
        age_time
    )

  

    total_loc, loc_time = perf_counter(
        loc_query,
        [
            "OWNER",
            "COLLABORATOR",
            "ORGANIZATION_MEMBER"
        ],
        0
    )

    if total_loc[-1]:

        formatter(
            "LOC (cached)",
            loc_time
        )

    else:

        formatter(
            "LOC (updated)",
            loc_time
        )

    

    commit_data, commit_time = perf_counter(
        commit_counter,
        0
    )

    formatter(
        "commit count",
        commit_time
    )

  

    star_data, star_time = perf_counter(
        graph_repos_stars,
        "stars",
        ["OWNER"]
    )

    formatter(
        "stars",
        star_time
    )


    repo_data, repo_time = perf_counter(
        graph_repos_stars,
        "repos",
        ["OWNER"]
    )

    formatter(
        "repositories",
        repo_time
    )

  
    contrib_data, contrib_time = perf_counter(
        graph_repos_stars,
        "repos",
        [
            "OWNER",
            "COLLABORATOR",
            "ORGANIZATION_MEMBER"
        ]
    )

    formatter(
        "contributed repos",
        contrib_time
    )



    follower_data, follower_time = perf_counter(
        follower_getter,
        USER_NAME
    )

    formatter(
        "followers",
        follower_time
    )

   
    for index in range(len(total_loc) - 1):

        total_loc[index] = "{:,}".format(
            total_loc[index]
        )

   
    svg_overwrite(
        "dark_mode.svg",
        age_data,
        commit_data,
        star_data,
        repo_data,
        contrib_data,
        follower_data,
        total_loc[:-1]
    )

    svg_overwrite(
        "light_mode.svg",
        age_data,
        commit_data,
        star_data,
        repo_data,
        contrib_data,
        follower_data,
        total_loc[:-1]
    )

   
    total_time = (
        user_time
        + age_time
        + loc_time
        + commit_time
        + star_time
        + repo_time
        + contrib_time
        + follower_time
    )

    print()
    print(
        "Total function time:",
        "%.4f" % total_time,
        "s"
    )

    print()
    print(
        "Total GitHub GraphQL API calls:",
        sum(QUERY_COUNT.values())
    )

    for function_name, count in QUERY_COUNT.items():

        print(
            "   {:<25} {}".format(
                function_name + ":",
                count
            )
        )

    print()
    print("SVG files updated successfully.")
