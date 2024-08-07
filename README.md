# flask-typescript

Keep your front-end and back-end in sync.

Remember: Python typing is currently a [dog's breakfast](https://www.google.com/search?q=dog%27s+breakfast) compared to Typescript.

Typescript for [flask](https://flask.palletsprojects.com/)
based on [FastAPI](https://fastapi.tiangolo.com) and
[pydantic](https://docs.pydantic.dev/) (on which this package depends).

Instead of generating OpenAPI schema, we generate typescript types since
-- we believe --
keeping the client javascript consistent with the backend python is the most
fraught part of web development.

Also, we want to make it easier to send `FormData`
data.

## Install

```python

python -m pip install flask-typescript
```

## Warning:

Please note that we are trying to ensure synchronization between python and
typescript "types" during an HTTP exchange of data. Because of the hysteresis
between the two languages and the serialisation requirements of JSON:
**only a subset of pydantic/typescript types will ever be supported**.
Keep it simple people -- you'll be happier, I'll be happier :).

In particular attributes that are `Callable`s will _not_ translate!

## Usage

```python
from flask import Flask
from flask_typescript import Api
from pydantic import BaseModel

app = Flask(__name__)
api = Api('Curators') # or any name you like

class User(BaseModel):
    name: str
    age: int

@app.post('/user_ok')
@api # mark this a part of your API
def user_ok(user:User) -> User:
    if user.age > 60:
        return User(name=user.name + ' Jr.', age=20)
    return user

# adds a `ts` subcommmand to flask
api.init_app(app)
```

You can run `flask ts` to generate some typescript types that can help keep your
javascript client code in sync with your python api.

Run (say) `flask ts typescript > src/flask-types.d.ts` and
`flask ts endpoints > src/endpoints.ts`

Then on the client we can do:

```typescript
import type { User, Curators } from "./flask-types"
import { Endpoints } from "./endpoints"

export user_ok: Curators.user_ok = async (user: User)  => {
  const resp = await fetch(Endpoints.Curators.user_ok.url(), {
    method: "post",
    body: JSON.stringify(user),
    headers: {
      "Content-Type": "application/json",
    },
  })
  if (!resp.ok) {
    throw new Error("no good!")
  }
  const reply = await resp.json()
  if (reply.type !== "success") {
    throw new Error("no good!")
  }
  return reply.result
}
const user: User = { name: "me", age: 61 }
const user2 = await user_ok(user)
user2.age === 20
```

The reason we separate `ts typescript` and `ts endpoints` is one produces
pure typescript types and so won't bloat the final bundled javascript whereas
the other generates some code that will.

## FormData

```typescript
import type { User } from "./types"
async function user_ok(formData: FormData): Promise<User> {
  const resp = await fetch("/user_ok", {
    method: "post",
    body: formData,
  })
  if (!resp.ok) {
    throw new Error("no good!")
  }
  const reply = await resp.json()
  if (reply.type !== "success") throw new Error("no good!")
  return reply.result as User
}
const login = document.forms["login"]
login.addEventListener("submit", async (e) => {
  e.preventDefault()
  const user2 = await user_ok(new FormData(login))
})
```

```html
<form name="login">
  name: <input name="name" type="text" required /> age:
  <input name="age" type="number" required min="0" />
  <button type="submit">Login</button>
</form>
```
