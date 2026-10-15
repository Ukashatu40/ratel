// Creates (or updates) RatelLink's MongoDB roles and user. Run it ONCE per environment by whoever
// administers MongoDB on core-cp, with an administrator account. See deploy/core-cp/README.md.
//
//   cd deploy/core-cp/mongo
//   RATEL_LINK_DB_PASSWORD='<a long random password>' \
//     mongosh "<administrator connection string>" --file create-ratel-link-user.js
//
// Run it from this folder (it reads ratel-link-roles.json from the current folder, or from the path
// in RATEL_LINK_ROLES_FILE).
//
// The password is read from the environment so it never appears in a command line, a shell history
// or this file. Generate one with:  openssl rand -base64 33 | tr -d '/+='
// Optional environment: RATEL_LINK_DB_USER (default ratel_link), RATEL_LINK_DB_NAME (default
// ratel_link), OPEN5GS_DB_NAME (default open5gs), RATEL_LINK_ROLE_SUFFIX (default empty).
//
// What the user may do is in ratel-link-roles.json. In short: RatelLink may read and write its own
// collections (never delete, and never change a stored key or an audit entry), and may read, insert
// and update the core's `subscribers` collection. It cannot remove anything, create indexes in the
// core's database, or touch any other collection or database.

const fs = require("fs");

const env = (name, fallback) => process.env[name] || fallback;
const password = process.env.RATEL_LINK_DB_PASSWORD;
if (!password || password.length < 24) {
  throw new Error("Set RATEL_LINK_DB_PASSWORD (at least 24 characters) in the environment.");
}
const user = env("RATEL_LINK_DB_USER", "ratel_link");
const values = {
  RATEL_DB: env("RATEL_LINK_DB_NAME", "ratel_link"),
  CORE_DB: env("OPEN5GS_DB_NAME", "open5gs"),
  SUFFIX: env("RATEL_LINK_ROLE_SUFFIX", ""),
};

let text = fs.readFileSync(env("RATEL_LINK_ROLES_FILE", "ratel-link-roles.json"), "utf8");
for (const [key, value] of Object.entries(values)) {
  text = text.split("{{" + key + "}}").join(value);
}
const spec = JSON.parse(text);

const admin = db.getSiblingDB("admin");
const names = [];
for (const role of spec.roles) {
  names.push(role.role);
  // The helpers throw on failure, so a half-applied run cannot look like success.
  if (admin.getRole(role.role)) {
    admin.updateRole(role.role, { privileges: role.privileges, roles: role.roles });
    print("updated role " + role.role);
  } else {
    admin.createRole({ role: role.role, privileges: role.privileges, roles: role.roles });
    print("created role " + role.role);
  }
}

const grants = names.map((role) => ({ role: role, db: "admin" }));
if (admin.getUser(user)) {
  admin.updateUser(user, { pwd: password, roles: grants });
  print("updated user " + user + " (password replaced)");
} else {
  admin.createUser({ user: user, pwd: password, roles: grants });
  print("created user " + user);
}
